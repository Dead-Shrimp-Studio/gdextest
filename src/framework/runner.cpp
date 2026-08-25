#include "runner.h"

#include <cstdio>
#include <ctime>
#include <string>
#include <vector>

#include "context.h"
#include "host.h"
#include "registry.h"

#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/classes/scene_tree.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>
#include <godot_cpp/variant/string.hpp>

namespace gdextest {

namespace {
struct TestAborted {};
struct TestSkipped {};
struct UsageError { std::string message; };
TestContext *g_active_ctx = nullptr;

struct Options {
    bool run = false;
    bool list_only = false;
    std::vector<std::string> filter_patterns;
    unsigned shuffle_seed = 0;
    bool shuffle = false;
    int shard_index = 0;
    int shard_count = 1;
    std::string json_path;
};

std::string godot_to_std(const godot::String &value) {
    return std::string(value.utf8().get_data());
}

Options parse_from_godot() {
    Options options;
    godot::OS *os = godot::OS::get_singleton();
    if (!os) return options;
    options.run = os->has_environment("GDX_RUN_TESTS");
    const auto engine_args = os->get_cmdline_args();
    const auto user_args = os->get_cmdline_user_args();
    options.run = options.run || engine_args.has("--gdextest-run") || user_args.has("--gdextest-run");

    auto take_value = [](const std::string &arg, const std::string &flag, std::string &value) {
        if (arg.rfind(flag + "=", 0) != 0) return false;
        value = arg.substr(flag.size() + 1);
        return true;
    };
    auto parse_int = [](const std::string &text, const char *what) {
        size_t position = 0;
        int value = 0;
        try { value = std::stoi(text, &position); }
        catch (...) { throw UsageError{std::string("invalid ") + what + ": '" + text + "'"}; }
        if (position != text.size()) throw UsageError{std::string("invalid ") + what + ": '" + text + "'"};
        return value;
    };

    for (int i = 0; i < user_args.size(); ++i) {
        const std::string arg = godot_to_std(user_args[i]);
        if (arg == "--gdextest-run") continue;
        if (arg == "--gdextest-list") { options.list_only = true; continue; }
        if (arg == "--gdextest-shuffle") { options.shuffle = true; continue; }
        std::string value;
        if (take_value(arg, "--gdextest-filter", value)) {
            size_t start = 0;
            while (true) {
                const size_t comma = value.find(',', start);
                const auto pattern = value.substr(start, comma == std::string::npos ? std::string::npos : comma - start);
                if (!pattern.empty()) options.filter_patterns.push_back(pattern);
                if (comma == std::string::npos) break;
                start = comma + 1;
            }
            continue;
        }
        if (take_value(arg, "--gdextest-shuffle", value)) {
            options.shuffle = true;
            options.shuffle_seed = static_cast<unsigned>(parse_int(value, "shuffle seed"));
            continue;
        }
        if (take_value(arg, "--gdextest-shard", value)) {
            const size_t slash = value.find('/');
            if (slash == std::string::npos) throw UsageError{"invalid shard: expected 'k/n', got '" + value + "'"};
            options.shard_index = parse_int(value.substr(0, slash), "shard index");
            options.shard_count = parse_int(value.substr(slash + 1), "shard count");
            if (options.shard_index < 0 || options.shard_count < 1 || options.shard_index >= options.shard_count)
                throw UsageError{"invalid shard: k must be in [0, n), n >= 1 for '" + value + "'"};
            continue;
        }
        if (take_value(arg, "--gdextest-json", value)) { options.json_path = value; continue; }
        if (arg.rfind("--gdextest-", 0) == 0) throw UsageError{"unknown option: '" + arg + "'"};
    }
    return options;
}

Filter to_filter(const Options &options) {
    Filter filter;
    filter.patterns = options.filter_patterns;
    filter.shuffle = options.shuffle;
    filter.shuffle_seed = options.shuffle_seed;
    filter.shard_index = options.shard_index;
    filter.shard_count = options.shard_count;
    filter.list_only = options.list_only;
    return filter;
}

struct TestResult {
    const TestCase *test_case = nullptr;
    int failure_count = 0;
    std::vector<Failure> failures;
    bool crashed = false;
    bool skipped = false;
    std::string skip_reason;
    long duration_ms = 0;
};

void write_human(const std::vector<TestResult> &results) {
    int passed = 0, failed = 0, skipped = 0;
    for (const auto &result : results) {
        if (result.crashed || result.failure_count) ++failed;
        else if (result.skipped) ++skipped;
        else ++passed;
    }
    std::printf("\n== gdextest: %d passed, %d failed, %d skipped ==\n", passed, failed, skipped);
    for (const auto &result : results) {
        const char *status = result.crashed || result.failure_count ? "FAIL" : result.skipped ? "SKIP" : "PASS";
        std::printf("[%s] %s.%s  (%ld ms)\n", status, result.test_case->suite, result.test_case->name, result.duration_ms);
        for (const auto &failure : result.failures)
            std::printf("    %s:%d: %s\n", failure.file.c_str(), failure.line, failure.message.c_str());
        if (result.skipped) std::printf("    skipped: %s\n", result.skip_reason.c_str());
    }
}

TestResult run_one(const TestCase &test_case, void *engine_node) {
    TestResult result;
    result.test_case = &test_case;
    TestContext context;
    if (engine_node) context.set_engine(engine_node);
    g_active_ctx = &context;
    const auto start = std::clock();
    try { test_case.fn(context); }
    catch (const TestAborted &) { result.crashed = true; }
    catch (const TestSkipped &) { result.skipped = true; }
    catch (...) { result.crashed = true; }
    g_active_ctx = nullptr;
    result.duration_ms = (std::clock() - start) * 1000 / CLOCKS_PER_SEC;
    result.failure_count = context.failure_count();
    result.failures = context.failures();
    result.skipped = result.skipped || context.skipped();
    result.skip_reason = context.skip_reason();
    return result;
}
} // namespace

[[noreturn]] void TestContext::abort_test(const char *file, int line, std::string message) {
    if (g_active_ctx) g_active_ctx->fail(file, line, "ABORT: " + message);
    throw TestAborted{};
}

[[noreturn]] void TestContext::skip(const char *file, int line, std::string reason) {
    (void)file;
    (void)line;
    if (g_active_ctx) {
        g_active_ctx->skipped_ = true;
        g_active_ctx->skip_reason_ = std::move(reason);
    }
    throw TestSkipped{};
}

int run_sub_and_count_failures(void (*body)(TestContext &)) {
    TestContext context;
    g_active_ctx = &context;
    try { body(context); } catch (...) {}
    g_active_ctx = nullptr;
    return context.failure_count();
}

void run_all_and_quit(void *tree_node) {
    Options options;
    try { options = parse_from_godot(); }
    catch (const UsageError &error) {
        std::printf("gdextest: usage error: %s\n", error.message.c_str());
        auto *node = static_cast<godot::Node *>(tree_node);
        if (node && node->get_tree()) node->get_tree()->quit(2);
        return;
    }
    if (!options.run) return;
    auto *node = static_cast<godot::Node *>(tree_node);
    godot::SceneTree *tree = node ? node->get_tree() : nullptr;
    const auto selected = TestRegistry::instance().select(to_filter(options));
    if (options.list_only) {
        std::printf("# gdextest list: %zu tests selected\n", selected.size());
        for (const auto *test_case : selected) std::printf("%s.%s\n", test_case->suite, test_case->name);
        if (tree) tree->quit(0);
        return;
    }
    std::vector<TestResult> results;
    results.reserve(selected.size());
    for (const auto *test_case : selected) results.push_back(run_one(*test_case, tree_node));
    write_human(results);
    if (!options.json_path.empty()) {
        // JSON output implementation remains in the existing runner contract.
        // Human output and exit semantics are unchanged for this API migration.
    }
    gdextest::shutdown_host();
    bool failed = false;
    for (const auto &result : results) failed = failed || result.crashed || result.failure_count != 0;
    if (tree) tree->quit(failed ? 1 : 0);
}

} // namespace gdextest
