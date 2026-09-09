// Runner: the Godot-facing test execution boundary (plan §5.5). Parses the
// --gdextest-* options, selects tests, and drives them to completion — sync
// bodies inline, async bodies (Milestone C) through a process_frame pump that
// resumes suspended coroutines — then writes human + JSON output and exits via
// SceneTree::quit(code) (0 = pass, 1 = failure, 2 = usage error).
#include "gdextest/runner.h"

#include <coroutine>
#include <cstdio>
#include <ctime>
#include <exception>
#include <string>
#include <utility>
#include <vector>

#include "gdextest/context.h"
#include "gdextest/host.h"
#include "gdextest/registry.h"

#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/classes/object.hpp>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/classes/scene_tree.hpp>
#include <godot_cpp/classes/time.hpp>
#include <godot_cpp/variant/callable_method_pointer.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>
#include <godot_cpp/variant/string.hpp>

namespace gdextest {

// Every line this runner prints to stdout inside the engine process carries
// this prefix (Milestone M3), so the CLI can separate framework output from
// Godot's own chatter in the captured stream. Consumers who drive Godot
// directly can grep for it, too.
inline constexpr const char *kGdxOutputMarker = "GDX_TEST_OUTPUT:";

void TestContext::track_object(void *obj) {
    auto *object = static_cast<godot::Object *>(obj);
    if (object) tracked_objects_.push_back({object->get_instance_id()});
}

void TestContext::track_ref(void *ref) {
    auto *counted = static_cast<godot::RefCounted *>(ref);
    if (counted) tracked_refs_.push_back({ref, counted->get_reference_count()});
}

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
    // Machine-friendly reporting (Milestone M3): `report_path` is an extra
    // JSON document the CLI (or any wrapper) reads after the process exits;
    // `report` selects the in-engine stdout verbosity. Defaults stay quiet —
    // the CLI renders the pretty report from the JSON document.
    std::string report_path;
    bool pretty_report = false;
    // Runtime budgets, populated from --gdextest-* flags (the CLI forwards the
    // consumer's [gdextest.test] keys). Defaults stay in sync with config.h.
    int timeout_ms = kDefaultTimeoutMs;
    int isolate_timeout_sec = kDefaultIsolateTimeoutSec;
    int flaky_retries = kDefaultFlakyRetries;
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
        if (take_value(arg, "--gdextest-report-path", value)) { options.report_path = value; continue; }
        if (take_value(arg, "--gdextest-report", value)) {
            if (value == "pretty") { options.pretty_report = true; }
            else if (value == "quiet") { options.pretty_report = false; }
            else { throw UsageError{"invalid report mode: '" + value + "' (expected pretty or quiet)"}; }
            continue;
        }
        if (take_value(arg, "--gdextest-timeout-ms", value)) {
            options.timeout_ms = parse_int(value, "timeout ms");
            if (options.timeout_ms <= 0) throw UsageError{"timeout ms must be positive"};
            continue;
        }
        if (take_value(arg, "--gdextest-isolate-timeout-sec", value)) {
            options.isolate_timeout_sec = parse_int(value, "isolate timeout seconds");
            if (options.isolate_timeout_sec <= 0) throw UsageError{"isolate timeout seconds must be positive"};
            continue;
        }
        if (take_value(arg, "--gdextest-flaky-retries", value)) {
            options.flaky_retries = parse_int(value, "flaky retries");
            if (options.flaky_retries < 0) throw UsageError{"flaky retries must be >= 0"};
            continue;
        }
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

// Prefix one output line with the framework marker. All runner stdout goes
// through this, so captured engine output is always separable from Godot's
// own chatter. Nothing is buffered: a crash may cut the tail short, but never
// reorders it.
void gdx_print(const std::string &text) {
    std::printf("%s %s\n", kGdxOutputMarker, text.c_str());
}

// Marker-prefix each physical line of `text` (failure messages embed newlines
// for their expected/actual operand lines).
void gdx_print_lines(const std::string &text) {
    size_t start = 0;
    while (true) {
        const size_t newline = text.find('\n', start);
        gdx_print(text.substr(start, newline == std::string::npos
                                         ? std::string::npos
                                         : newline - start));
        if (newline == std::string::npos) break;
        start = newline + 1;
    }
}

struct TestResult {
    const TestCase *test_case = nullptr;
    int failure_count = 0;
    int retries = 0;
    std::vector<Failure> failures;
    bool crashed = false;
    bool skipped = false;
    std::string skip_reason;
    long duration_ms = 0;
};

// In-engine stdout report. Quiet (default): a summary line plus one line per
// test with its failure/skip detail — extraction fodder for wrappers. Pretty:
// the same content, laid out for consumers driving Godot directly. Every
// physical line is marker-prefixed in both variants; colors stay out of the
// engine entirely.
void write_report(const std::vector<TestResult> &results, bool pretty) {
    (void)pretty;   // both variants share one content layout today
    int passed = 0, failed = 0, skipped = 0;
    for (const auto &result : results) {
        if (result.crashed || result.failure_count) ++failed;
        else if (result.skipped) ++skipped;
        else ++passed;
    }
    gdx_print("== gdextest: " + std::to_string(passed) + " passed, " +
              std::to_string(failed) + " failed, " + std::to_string(skipped) +
              " skipped ==");
    for (const auto &result : results) {
        const char *status = result.crashed || result.failure_count ? "FAIL"
                           : result.skipped ? "SKIP" : "PASS";
        std::string line = std::string("[") + status + "] " +
                           result.test_case->suite + "." + result.test_case->name +
                           "  (" + std::to_string(result.duration_ms) + " ms)";
        if (result.retries) line += "  (retries: " + std::to_string(result.retries) + ")";
        gdx_print(line);
        for (const auto &failure : result.failures) {
            gdx_print_lines("    " + failure.file + ":" +
                            std::to_string(failure.line) + ": " +
                            failure.message);
        }
        if (result.skipped && !result.skip_reason.empty())
            gdx_print_lines("    skipped: " + result.skip_reason);
    }
}

// JSON-escape a string per RFC 8259: quotes, backslashes, and control characters.
std::string esc_json(const std::string &s) {
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
                    char buffer[8];
                    std::snprintf(buffer, sizeof buffer, "\\u%04x", c);
                    out += buffer;
                } else {
                    out += c;
                }
        }
    }
    return out;
}

// Machine-readable results per docs/cli.md. A crashed test also counts toward
// `fail`; a skipped test carries an optional `reason` and never counts as fail.
void write_json(const std::string &path, const std::vector<TestResult> &results) {
    std::FILE *fp = std::fopen(path.c_str(), "wb");
    if (!fp) return;
    int pass = 0, fail = 0, skip = 0, crashed = 0;
    for (const auto &result : results) {
        if (result.crashed) { ++crashed; ++fail; }
        else if (result.failure_count != 0) ++fail;
        else if (result.skipped) ++skip;
        else ++pass;
    }
    std::fprintf(fp, "{\"totals\":{\"pass\":%d,\"fail\":%d,\"skip\":%d,\"crashed\":%d},\"results\":[",
                 pass, fail, skip, crashed);
    for (size_t i = 0; i < results.size(); ++i) {
        const TestResult &result = results[i];
        const char *status = result.crashed ? "crashed"
                           : result.failure_count != 0 ? "fail"
                           : result.skipped ? "skipped" : "pass";
        std::fprintf(fp, "%s{\"suite\":\"%s\",\"name\":\"%s\",\"status\":\"%s\"",
                     i ? "," : "", esc_json(result.test_case->suite).c_str(),
                     esc_json(result.test_case->name).c_str(), status);
        if (result.skipped && !result.skip_reason.empty()) {
            std::fprintf(fp, ",\"reason\":\"%s\"", esc_json(result.skip_reason).c_str());
        }
        std::fprintf(fp, ",\"duration_ms\":%ld,\"retries\":%d,\"failures\":[", result.duration_ms, result.retries);
        for (size_t j = 0; j < result.failures.size(); ++j) {
            const Failure &failure = result.failures[j];
            std::fprintf(fp, "%s{\"file\":\"%s\",\"line\":%d,\"message\":\"%s\"}",
                         j ? "," : "", esc_json(failure.file).c_str(), failure.line,
                         esc_json(failure.message).c_str());
        }
        std::fprintf(fp, "]}");
    }
    std::fprintf(fp, "]}");
    std::fclose(fp);
}

void check_tracked_resources_impl(TestContext &context) {
    for (const auto &tracked : context.tracked_objects()) {
        if (godot::UtilityFunctions::instance_from_id(static_cast<int64_t>(tracked.id))) {
            context.fail("", 0, "leak: tracked Object instance " + std::to_string(tracked.id) + " is still alive");
        }
    }
    for (const auto &tracked : context.tracked_refs()) {
        auto *ref = static_cast<godot::RefCounted *>(tracked.ptr);
        if (!ref) continue;
        // A RefCounted reaching zero is the expected clean teardown state. Do
        // not dereference it after unreference; a stale wrapper is a UAF only
        // when the test explicitly records a dead object before teardown.
        const int32_t count = ref->get_reference_count();
        if (count > tracked.initial_count) {
            context.fail("", 0, "leak: tracked RefCounted reference count increased from " +
                                  std::to_string(tracked.initial_count) + " to " +
                                  std::to_string(count));
        }
    }
}

// Runs the test's registered teardowns in reverse registration order (LIFO).
// A throwing teardown is recorded as a failure but never prevents the remaining
// ones; called before the tracked-object/ref leak checks so teardowns can free
// resources first.
void run_teardowns(TestContext &context) {
    for (auto it = context.teardowns().rbegin(); it != context.teardowns().rend(); ++it) {
        try { (*it)(); }
        catch (...) { context.fail("", 0, "teardown threw an exception"); }
    }
}

TestResult run_one(const TestCase &test_case, void *engine_node) {
    TestResult result;
    result.test_case = &test_case;
    const auto start = std::clock();
    const int max_retries = (test_case.tags & TAG_FLAKY) ? runtime_config().flaky_retries : 0;
    for (int attempt = 0; attempt <= max_retries; ++attempt) {
        TestContext context;
        if (engine_node) context.set_engine(engine_node);
        g_active_ctx = &context;
        try { test_case.fn(context); }
        catch (const TestAborted &) { /* failure is already recorded */ }
        catch (const TestSkipped &) { /* context carries skip state */ }
        catch (...) { context.fail(test_case.file, test_case.line, "unexpected exception in test body"); }
        run_teardowns(context);
        check_tracked_resources_impl(context);
        g_active_ctx = nullptr;
        result.failure_count = context.failure_count();
        result.failures = context.failures();
        result.skipped = context.skipped();
        result.skip_reason = context.skip_reason();
        if (result.skipped || result.failure_count == 0) {
            result.retries = attempt;
            break;
        }
        result.retries = attempt;
    }
    result.duration_ms = (std::clock() - start) * 1000 / CLOCKS_PER_SEC;
    return result;
}

// --- async frame pump (plan §7.2, Milestone C) -------------------------------
// Sync tests still run inline. An async test is a coroutine: the runner starts
// it, and when it co_awaits, the pump registers a process_frame callback and
// returns control to the engine main loop. Each frame advances the current await
// (frames remaining / elapsed time) and resumes the coroutine when it resolves.
// Tests run one at a time in declaration order; timeouts are enforced per wait
// (kDefaultTimeoutMs) and per test (kDefaultIsolateTimeoutSec).

struct RunState {
    Options options;
    godot::SceneTree *tree = nullptr;
    godot::Node *tree_node = nullptr;
    std::vector<const TestCase *> selected;
    std::vector<TestResult> results;
    size_t next = 0;

    // The async test currently suspended in the pump (one at a time).
    const TestCase *current_case = nullptr;
    TestContext current_ctx;
    Task current_task;
    int64_t test_start_ms = 0;

    godot::Callable frame_callable;
    bool connected = false;
};

RunState *g_run = nullptr;

int64_t now_ms() {
    godot::Time *time = godot::Time::get_singleton();
    return time ? static_cast<int64_t>(time->get_ticks_msec()) : 0;
}

std::string async_test_label(const TestCase *tc) {
    return std::string(tc->suite) + "." + std::string(tc->name);
}

void start_next_test(RunState &run);
void finish_run(RunState *run);
void on_engine_frame();

// Collects the finished current async test into `run.results` and releases its
// coroutine frame. The caller (on_engine_frame or start_next_test's loop)
// advances to the next selected test.
void collect_async_result(RunState &run) {
    run_teardowns(run.current_ctx);
    check_tracked_resources_impl(run.current_ctx);
    TestResult result;
    result.test_case = run.current_case;
    bool crashed = false;
    bool skipped = false;
    if (std::exception_ptr exception = run.current_task.exception()) {
        try { std::rethrow_exception(exception); }
        catch (const TestAborted &) { crashed = true; }
        catch (const TestSkipped &) { skipped = true; }
        catch (...) { crashed = true; }
    }
    result.crashed = crashed;
    result.skipped = skipped || run.current_ctx.skipped();
    result.skip_reason = run.current_ctx.skip_reason();
    result.failure_count = run.current_ctx.failure_count();
    result.failures = run.current_ctx.failures();
    result.duration_ms = now_ms() - run.test_start_ms;
    run.results.push_back(std::move(result));

    g_active_ctx = nullptr;
    AsyncCoordinator::instance().clear();
    run.current_task = Task{};   // destroys the completed coroutine frame
    run.current_case = nullptr;
    run.current_ctx = TestContext{};
    // The caller (on_engine_frame or start_next_test's loop) advances to the
    // next test — never finish the run from here (start_next_test owns that).
}

// Fails the current async test with `message` (a timeout / isolate breach) and
// releases its suspended coroutine frame. The caller advances to the next test.
void fail_current_async(RunState &run, std::string message) {
    run_teardowns(run.current_ctx);
    check_tracked_resources_impl(run.current_ctx);
    run.current_ctx.fail(run.current_case ? run.current_case->file : "",
                         run.current_case ? run.current_case->line : 0,
                         std::move(message));
    check_tracked_resources_impl(run.current_ctx);
    TestResult result;
    result.test_case = run.current_case;
    result.failure_count = run.current_ctx.failure_count();
    result.failures = run.current_ctx.failures();
    result.duration_ms = now_ms() - run.test_start_ms;
    run.results.push_back(std::move(result));

    g_active_ctx = nullptr;
    AsyncCoordinator::instance().clear();
    run.current_task = Task{};   // destroys the suspended coroutine frame
    run.current_case = nullptr;
    run.current_ctx = TestContext{};
    // The caller advances to the next test (same rule as collect_async_result).
}

void ensure_connected(RunState &run) {
    if (run.connected || !run.tree) return;
    // callable_mp_static is a macro; it must be used unqualified.
    run.frame_callable = callable_mp_static(&on_engine_frame);
    run.tree->connect("process_frame", run.frame_callable);
    run.connected = true;
}

// One engine process_frame tick: advance the current await, resume the suspended
// coroutine when the await resolves, and enforce the time budgets.
void on_engine_frame() {
    RunState *run = g_run;
    if (!run || !run->current_case) return;
    // The engine pump owns the driver flag for the duration of its async tests.
    // Sync tests (self-tests) run inline and may temporarily toggle it; re-assert
    // it here so every engine-driven await suspends as expected.
    AsyncCoordinator::instance().set_driver_active(true);
    const int64_t now = now_ms();
    const AwaitStatus status = AsyncCoordinator::instance().advance(now);
    if (status == AwaitStatus::Pending) {
        // Whole-test isolate budget: a chain of awaits must not run forever even
        // when each individual wait is under its own per-wait timeout.
        if (now - run->test_start_ms >= static_cast<int64_t>(runtime_config().isolate_timeout_sec) * 1000) {
            fail_current_async(*run, "async test '" + async_test_label(run->current_case) +
                               "' exceeded the per-test isolate timeout of " +
                               std::to_string(runtime_config().isolate_timeout_sec) + " s");
            start_next_test(*run);
        }
        return;
    }
    if (status == AwaitStatus::TimedOut) {
        const AwaitRequest &request = AsyncCoordinator::instance().request();
        fail_current_async(*run, "async test '" + async_test_label(run->current_case) +
                           "' timed out: " + request.description + " did not resolve within " +
                           std::to_string(request.timeout_ms) + " ms");
        start_next_test(*run);
        return;
    }
    // The await resolved: resume the suspended coroutine.
    std::coroutine_handle<> handle = AsyncCoordinator::instance().current();
    handle.resume();
    if (handle.done()) {
        collect_async_result(*run);
        start_next_test(*run);
        return;
    }
    // Resumed into another await; stamp its deadlines with the current clock.
    AsyncCoordinator::instance().stamp(now);
}

// Runs sync tests inline; for an async test, starts its coroutine and, if it
// suspends, connects the pump and waits for engine frames. Finishes the run
// when no tests remain.
void start_next_test(RunState &run) {
    while (run.next < run.selected.size()) {
        const TestCase *tc = run.selected[run.next++];
        if (!tc->async_fn) {
            run.results.push_back(run_one(*tc, run.tree_node));
            continue;
        }
        // Async test: start the coroutine and run it until its first suspension.
        // Re-assert the driver flag: sync tests that ran earlier (self-tests)
        // may have cleared it via their own transient pumps.
        AsyncCoordinator::instance().set_driver_active(true);
        run.current_case = tc;
        run.current_ctx = TestContext{};
        if (run.tree_node) run.current_ctx.set_engine(run.tree_node);
        run.test_start_ms = now_ms();
        g_active_ctx = &run.current_ctx;
        run.current_task = tc->async_fn(run.current_ctx);
        run.current_task.resume();
        if (run.current_task.done()) {
            collect_async_result(run);
            continue;   // completed without suspending; start the next test
        }
        // Suspended: stamp the await's deadlines, then wait for engine frames.
        AsyncCoordinator::instance().stamp(run.test_start_ms);
        if (!run.tree) {
            fail_current_async(run, "async test '" + async_test_label(tc) +
                               "' suspended but no live SceneTree is available to drive frames");
            continue;
        }
        ensure_connected(run);
        return;   // control returns to the engine main loop; the pump resumes us
    }
    finish_run(&run);
}

void finish_run(RunState *run) {
    if (run->connected) {
        run->tree->disconnect("process_frame", run->frame_callable);
        run->connected = false;
    }
    // JSON documents first (flushed before any printing), so a crash during
    // reporting cannot lose the machine-readable results.
    if (!run->options.report_path.empty()) write_json(run->options.report_path, run->results);
    if (!run->options.json_path.empty()) write_json(run->options.json_path, run->results);
    write_report(run->results, run->options.pretty_report);
    gdextest::shutdown_host();
    bool failed = false;
    for (const auto &result : run->results) {
        failed = failed || result.crashed || result.failure_count != 0;
    }
    AsyncCoordinator::instance().set_driver_active(false);
    g_run = nullptr;
    if (run->tree) run->tree->quit(failed ? 1 : 0);
    delete run;
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
    run_teardowns(context);
    g_active_ctx = nullptr;
    return context.failure_count();
}

int run_sub_and_write_json(void (*body)(TestContext &), const char *path) {
    TestContext context;
    g_active_ctx = &context;
    try { body(context); } catch (...) {}
    run_teardowns(context);
    g_active_ctx = nullptr;
    // Synthetic case so the JSON document has a suite/name; the self-tests only
    // assert on status/totals/failures/reason, not on these identifiers.
    static const TestCase sub_case{"self", "json_sub", nullptr, nullptr, TAG_UNIT, "", 0};
    TestResult result;
    result.test_case = &sub_case;
    check_tracked_resources_impl(context);
    result.failure_count = context.failure_count();
    result.failures = context.failures();
    result.skipped = context.skipped();
    result.skip_reason = context.skip_reason();
    const std::vector<TestResult> results{result};
    write_json(path, results);
    return result.failure_count;
}

bool SubAsyncPump::start(std::function<Task(TestContext &)> body, TestContext &ctx) {
    ctx_ = &ctx;
    now_ms_ = 0;
    test_start_ms_ = 0;
    AsyncCoordinator::instance().set_driver_active(true);
    g_active_ctx = &ctx;
    task_ = body(ctx);
    task_.resume();
    if (task_.done()) {
        finish();
        return false;
    }
    AsyncCoordinator::instance().stamp(now_ms_);
    return true;
}

bool SubAsyncPump::step(int64_t tick_ms) {
    if (!ctx_) return false;   // not started, or already finished
    now_ms_ += tick_ms;
    const AwaitStatus status = AsyncCoordinator::instance().advance(now_ms_);
    if (status == AwaitStatus::Pending) {
        if (now_ms_ - test_start_ms_ >= static_cast<int64_t>(runtime_config().isolate_timeout_sec) * 1000) {
            ctx_->fail("", 0, "async test exceeded the per-test isolate timeout of " +
                              std::to_string(runtime_config().isolate_timeout_sec) + " s");
            finish();
            return false;
        }
        return true;
    }
    if (status == AwaitStatus::TimedOut) {
        const AwaitRequest &request = AsyncCoordinator::instance().request();
        ctx_->fail("", 0, "async test timed out: " + request.description +
                          " did not resolve within " + std::to_string(request.timeout_ms) + " ms");
        finish();
        return false;
    }
    task_.resume();
    if (task_.done()) {
        finish();
        return false;
    }
    AsyncCoordinator::instance().stamp(now_ms_);
    return true;
}

void SubAsyncPump::finish() {
    if (std::exception_ptr exception = task_.exception()) {
        try { std::rethrow_exception(exception); }
        catch (const TestAborted &) { /* failure already recorded on ctx_ */ }
        catch (const TestSkipped &) { /* ctx_->skipped() set by skip() */ }
        catch (const std::exception &error) {
            ctx_->fail("", 0, std::string("unexpected exception in async test body: ") + error.what());
        }
        catch (...) {
            ctx_->fail("", 0, "unexpected exception in async test body");
        }
    }
    if (ctx_) run_teardowns(*ctx_);
    g_active_ctx = nullptr;
    AsyncCoordinator::instance().clear();
    AsyncCoordinator::instance().set_driver_active(false);
    task_ = Task{};
    ctx_ = nullptr;
}

int run_sub_async_write_json(std::function<Task(TestContext &)> body, const char *path) {
    TestContext context;
    SubAsyncPump pump;
    pump.start(body, context);
    int guard = 0;
    while (pump.step(16) && ++guard < 100000) {}
    // Synthetic case so the JSON document has a suite/name (see run_sub_and_write_json).
    static const TestCase sub_case{"self", "json_sub_async", nullptr, nullptr, TAG_UNIT, "", 0};
    TestResult result;
    result.test_case = &sub_case;
    check_tracked_resources_impl(context);
    result.failure_count = context.failure_count();
    result.failures = context.failures();
    result.skipped = context.skipped();
    result.skip_reason = context.skip_reason();
    const std::vector<TestResult> results{result};
    write_json(path, results);
    return result.failure_count;
}

void run_all_and_quit(void *tree_node) {
    Options options;
    try { options = parse_from_godot(); }
    catch (const UsageError &error) {
        gdx_print("gdextest: usage error: " + error.message);
        auto *node = static_cast<godot::Node *>(tree_node);
        if (node && node->get_tree()) node->get_tree()->quit(2);
        return;
    }
    // Apply the runtime budgets before any test runs; async waits read them
    // when their own timeout_ms argument is left at 0 (the default).
    runtime_config().timeout_ms = options.timeout_ms;
    runtime_config().isolate_timeout_sec = options.isolate_timeout_sec;
    runtime_config().flaky_retries = options.flaky_retries;
    if (!options.run) return;
    auto *node = static_cast<godot::Node *>(tree_node);
    godot::SceneTree *tree = node ? node->get_tree() : nullptr;
    const auto selected = TestRegistry::instance().select(to_filter(options));
    if (options.list_only) {
        gdx_print("# gdextest list: " + std::to_string(selected.size()) + " tests selected");
        for (const auto *test_case : selected)
            gdx_print(std::string(test_case->suite) + "." + test_case->name);
        if (tree) tree->quit(0);
        return;
    }
    auto *run = new RunState;
    run->options = std::move(options);
    run->tree = tree;
    run->tree_node = static_cast<godot::Node *>(tree_node);
    run->selected = selected;
    run->results.reserve(selected.size());
    // The driver flag is asserted by start_next_test / on_engine_frame right
    // before each async resume, and cleared in finish_run.
    g_run = run;
    start_next_test(*run);
}

} // namespace gdextest
