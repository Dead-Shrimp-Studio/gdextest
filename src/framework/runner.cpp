#include "runner.h"

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "context.h"
#include "registry.h"

// Godot boundary — only this TU in the framework core needs these.
#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/classes/scene_tree.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>
#include <godot_cpp/variant/string.hpp>

namespace gdextest {

namespace {

struct TestAborted {};

// Thrown by TestContext::skip; caught inside the runner's own frame (same
// lifecycle as TestAborted) so the rest of the skipped body does not run.
struct TestSkipped {};

// Raised by flag parsing on malformed/unknown --gdxtest-* input; the runner
// catches it and quits with the reserved usage-error code 2.
struct UsageError {
    std::string message;
};

// Single-threaded; the runner sets this before invoking each body so GDX_ABORT_TEST
// (static method, no ctx ref) can record on the active context before throwing.
// (thread_local would be the M2 choice once async continuations land; M1 is sync-only.)
static TestContext *g_active_ctx = nullptr;

} // namespace

[[noreturn]] void TestContext::abort_test(const char *file, int line, std::string message) {
    if (g_active_ctx) {
        g_active_ctx->fail(file, line, "ABORT: " + message);
    }
    throw TestAborted{};
}

[[noreturn]] void TestContext::skip(const char *file, int line, std::string reason) {
    (void)file; (void)line;   // the reason is the user-visible payload for a skip
    if (g_active_ctx) {
        g_active_ctx->skipped_ = true;
        g_active_ctx->skip_reason_ = std::move(reason);
    }
    throw TestSkipped{};
}

namespace {

// --- flag parsing ----------------------------------------------------------
struct Options {
    bool run = false;               // trigger present
    bool list_only = false;
    std::vector<std::string> filter_patterns;
    unsigned shuffle_seed = 0;
    bool shuffle = false;
    int shard_index = 0, shard_count = 1;
    std::string json_path;          // empty = no JSON file
    bool human = true;
};

static std::string godot_to_std(const godot::String &s) {
    // String::utf8() returns CharString; .get_data() is the C string.
    return std::string(s.utf8().get_data());
}

static Options parse_from_godot() {
    Options o;
    godot::OS *os = godot::OS::get_singleton();
    if (!os) return o;

    // Trigger: env var, or --gdxtest-run in EITHER cmdline list (plan §3, M0-verified).
    if (os->has_environment("GDX_RUN_TESTS")) {
        o.run = true;
    }
    godot::PackedStringArray eng = os->get_cmdline_args();         // before "--"
    godot::PackedStringArray usr = os->get_cmdline_user_args();   // after "--"
    auto has = [](const godot::PackedStringArray &a, const char *tok) -> bool {
        return a.has(godot::String(tok));
    };
    if (has(eng, "--gdxtest-run") || has(usr, "--gdxtest-run")) o.run = true;

    // Walk user args for option flags (--gdxtest-*). Values come as "--flag=value" or
    // "--flag value"; we support the = form for filter/shard/shuffle/json. Malformed
    // values raise UsageError -> exit code 2 (plan: usage error).
    auto take_value = [](const std::string &arg, const std::string &flag,
                         std::string &out) -> bool {
        if (arg.rfind(flag + "=", 0) == 0) { out = arg.substr(flag.size() + 1); return true; }
        return false;
    };
    // Strict integer parse: must consume the whole token, else it is a usage error.
    auto parse_int = [](const std::string &s, const char *what) -> int {
        size_t pos = 0;
        int v = 0;
        try {
            v = std::stoi(s, &pos);
        } catch (...) {
            throw UsageError{std::string("invalid ") + what + ": '" + s + "'"};
        }
        if (pos != s.size()) {
            throw UsageError{std::string("invalid ") + what + ": '" + s + "'"};
        }
        return v;
    };

    for (int i = 0; i < usr.size(); ++i) {
        std::string a = godot_to_std(usr[i]);
        if (a == "--gdxtest-run") { continue; }               // trigger (already detected above)
        if (a == "--gdxtest-list") { o.list_only = true; continue; }
        if (a == "--gdxtest-shuffle") { o.shuffle = true; continue; }
        std::string v;
        if (take_value(a, "--gdxtest-filter", v)) {
            // Comma-separated; "-foo" is a negative.
            size_t start = 0;
            do {
                size_t comma = v.find(',', start);
                std::string pat = v.substr(start, comma == std::string::npos
                                                  ? std::string::npos : comma - start);
                if (!pat.empty()) o.filter_patterns.push_back(pat);
                if (comma == std::string::npos) break;
                start = comma + 1;
            } while (true);
            continue;
        }
        if (take_value(a, "--gdxtest-shuffle", v)) {
            o.shuffle = true;
            o.shuffle_seed = static_cast<unsigned>(parse_int(v, "shuffle seed"));
            continue;
        }
        if (take_value(a, "--gdxtest-shard", v)) {
            auto slash = v.find('/');
            if (slash == std::string::npos) {
                throw UsageError{"invalid shard: expected 'k/n', got '" + v + "'"};
            }
            o.shard_index = parse_int(v.substr(0, slash), "shard index");
            o.shard_count = parse_int(v.substr(slash + 1), "shard count");
            if (o.shard_index < 0 || o.shard_count < 1 || o.shard_index >= o.shard_count) {
                throw UsageError{"invalid shard: k must be in [0, n), n >= 1 for '" + v + "'"};
            }
            continue;
        }
        if (take_value(a, "--gdxtest-json", v)) { o.json_path = v; continue; }
        // Any other recognized trigger/option prefix we don't know is a usage error.
        if (a.rfind("--gdxtest-", 0) == 0) {
            throw UsageError{"unknown option: '" + a + "'"};
        }
    }
    return o;
}

// Build a Filter from parsed Options. Exposed via count_selected_for_argv is overkill for M1;
// the self suite exercises the registry directly. Kept here for clarity.
static Filter to_filter(const Options &o) {
    Filter f;
    f.patterns = o.filter_patterns;
    f.shuffle = o.shuffle;
    f.shuffle_seed = o.shuffle_seed;
    f.shard_index = o.shard_index;
    f.shard_count = o.shard_count;
    f.list_only = o.list_only;
    return f;
}

// --- output ----------------------------------------------------------------
struct TestResult {
    const TestCase *tc;
    int failure_count = 0;
    std::vector<Failure> failures;
    bool crashed = false;     // body threw TestAborted or threw otherwise
    bool skipped = false;     // body called GDX_SKIP (recorded, not pass/fail)
    std::string skip_reason;
    long duration_ms = 0;
};

static std::string esc_json(const std::string &s) {
    std::string out;
    out.reserve(s.size() + 4);
    for (char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    char buf[8]; std::snprintf(buf, sizeof buf, "\\u%04x", c);
                    out += buf;
                } else {
                    out += c;
                }
        }
    }
    return out;
}

static void write_human(const std::vector<TestResult> &results) {
    int passed = 0, failed = 0, skipped = 0;
    for (const auto &r : results) {
        if (r.crashed || r.failure_count != 0) ++failed;
        else if (r.skipped) ++skipped;
        else ++passed;
    }
    std::printf("\n== gdextest: %d passed, %d failed, %d skipped ==\n", passed, failed, skipped);
    for (const auto &r : results) {
        const char *status;
        if (r.crashed || r.failure_count != 0) status = "FAIL";
        else if (r.skipped) status = "SKIP";
        else status = "PASS";
        std::printf("[%s] %s.%s  (%ld ms)\n", status, r.tc->suite, r.tc->name, r.duration_ms);
        for (const auto &f : r.failures) {
            std::printf("    %s:%d: %s\n", f.file.c_str(), f.line, f.message.c_str());
        }
        if (r.skipped) {
            std::printf("    skipped: %s\n", r.skip_reason.c_str());
        }
        if (r.crashed && r.failure_count == 0) {
            std::printf("    (test body aborted/crashed)\n");
        }
    }
}

static void write_json(const std::string &path, const std::vector<TestResult> &results) {
    std::FILE *fp = std::fopen(path.c_str(), "wb");
    if (!fp) return;
    int pass = 0, fail = 0, skip = 0, crashed = 0;
    for (const auto &r : results) {
        if (r.crashed) { ++crashed; ++fail; }
        else if (r.failure_count != 0) ++fail;
        else if (r.skipped) ++skip;
        else ++pass;
    }
    std::fprintf(fp, "{\"totals\":{\"pass\":%d,\"fail\":%d,\"skip\":%d,\"crashed\":%d},\"results\":[",
                 pass, fail, skip, crashed);
    for (size_t i = 0; i < results.size(); ++i) {
        const auto &r = *results[i].tc;
        std::string status;
        if (results[i].crashed) status = "crashed";
        else if (results[i].failure_count != 0) status = "fail";
        else if (results[i].skipped) status = "skipped";
        else status = "pass";
        std::fprintf(fp, "%s{\"suite\":\"%s\",\"name\":\"%s\",\"status\":\"%s\"",
                     i ? "," : "", esc_json(r.suite).c_str(), esc_json(r.name).c_str(),
                     status.c_str());
        if (results[i].skipped) {
            std::fprintf(fp, ",\"reason\":\"%s\"", esc_json(results[i].skip_reason).c_str());
        }
        std::fprintf(fp, ",\"duration_ms\":%ld,\"failures\":[", results[i].duration_ms);
        for (size_t j = 0; j < results[i].failures.size(); ++j) {
            const Failure &f = results[i].failures[j];
            std::fprintf(fp, "%s{\"file\":\"%s\",\"line\":%d,\"message\":\"%s\"}",
                         j ? "," : "",
                         esc_json(f.file).c_str(), f.line, esc_json(f.message).c_str());
        }
        std::fprintf(fp, "]}");
    }
    std::fprintf(fp, "]}");
    std::fclose(fp);
}

// --- run one test body -----------------------------------------------------
static TestResult run_one(const TestCase &tc, void *engine_node) {
    TestResult r; r.tc = &tc;
    TestContext ctx;
    if (engine_node) ctx.set_engine(engine_node);   // expose engine to integration bodies
    g_active_ctx = &ctx;
    auto t0 = std::clock();   // process time; good enough for M1 relative durations
    try {
        tc.fn(ctx);          // runner-injected ctx (chosen ctx-access model, plan §5.2)
    } catch (const TestAborted &) {
        r.crashed = true;
    } catch (const TestSkipped &) {
        r.skipped = true;    // recorded on ctx; not a pass and not a failure
    } catch (...) {
        r.crashed = true;
    }
    g_active_ctx = nullptr;
    auto t1 = std::clock();
    r.duration_ms = (t1 - t0) * 1000 / CLOCKS_PER_SEC;
    r.failure_count = ctx.failure_count();
    r.failures = ctx.failures();
    r.skipped = r.skipped || ctx.skipped();
    r.skip_reason = ctx.skip_reason();
    return r;
}

} // namespace

int run_sub_and_count_failures(void (*body)(TestContext &)) {
    TestContext ctx;
    g_active_ctx = &ctx;
    try { body(ctx); } catch (...) {}
    g_active_ctx = nullptr;
    return ctx.failure_count();
}

void run_all_and_quit(void *tree_node) {
    Options o;
    try {
        o = parse_from_godot();
    } catch (const UsageError &e) {
        std::printf("gdxtest: usage error: %s\n", e.message.c_str());
        godot::Node *node = static_cast<godot::Node *>(tree_node);
        godot::SceneTree *tree = node ? node->get_tree() : nullptr;
        if (tree) tree->quit(2);   // reserved usage-error exit code (plan §3)
        return;
    }
    if (!o.run) return;   // no trigger — normal startup continues (plan §3)

    godot::Node *node = static_cast<godot::Node *>(tree_node);
    godot::SceneTree *tree = node ? node->get_tree() : nullptr;
    // tree may be null only if invoked before the tree is live — adapter must not do that
    // (M0-verified hook points). We still proceed to run tests; quit() needs a non-null tree.

    std::vector<const TestCase *> selected = TestRegistry::instance().select(to_filter(o));

    if (o.list_only) {
        std::printf("# gdxtest list: %zu tests selected\n", selected.size());
        for (const TestCase *tc : selected) {
            std::printf("%s.%s\n", tc->suite, tc->name);
        }
        if (tree) tree->quit(0);
        return;
    }

    std::vector<TestResult> results;
    results.reserve(selected.size());
    for (const TestCase *tc : selected) {
        results.push_back(run_one(*tc, tree_node));
    }

    write_human(results);
    if (!o.json_path.empty()) write_json(o.json_path, results);

    int failures = 0;
    for (const auto &r : results) {
        if (r.failure_count != 0 || r.crashed) ++failures;
    }
    if (tree) tree->quit(failures ? 1 : 0);
}

} // namespace gdextest
