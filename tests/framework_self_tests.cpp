// Framework self-tests (plan §12, category "self"). Verifies the framework's own
// behavior before any host code trusts it. Compiled only under GDEXTEST_ENABLED.
#ifdef GDEXTEST_ENABLED

#include <algorithm>
#include <cstdio>   // std::remove
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace {
int g_flaky_attempts = 0;
}

#include "framework/assert.h"
#include "framework/registry.h"
#include "framework/host.h"
#include "framework/runner.h"

namespace {
// Read a file written by run_sub_and_write_json (paths resolve against the
// runner's cwd).
std::string read_file(const char *path) {
    std::ifstream in(path, std::ios::binary);
    std::ostringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}
}

namespace {
bool bootstrap_called = false;
bool shutdown_called = false;
void mark_bootstrap() { bootstrap_called = true; }
void mark_shutdown() { shutdown_called = true; }
}

GDEX_TEST_T(self, flaky_test_passes_after_retries, TAG_UNIT | TAG_FLAKY) {
    ++g_flaky_attempts;
    if (g_flaky_attempts < 3) GDEX_FAIL("intentional flaky failure");
}

GDEX_TEST(self, flaky_retry_metadata_is_registered) {
    const auto &cases = gdextest::TestRegistry::instance().all();
    bool found = false;
    for (const auto &test_case : cases) {
        if (std::string(test_case.name) == "flaky_test_passes_after_retries") {
            found = true;
            GDEX_EXPECT_TRUE((test_case.tags & gdextest::TAG_FLAKY) != 0);
        }
    }
    GDEX_EXPECT_TRUE(found);
}

GDEX_TEST(self, host_config_invokes_portable_callbacks) {
    bootstrap_called = false;
    shutdown_called = false;
    gdextest::configure_host({&mark_bootstrap, &mark_shutdown});
    gdextest::bootstrap_host();
    gdextest::shutdown_host();
    GDEX_EXPECT_TRUE(bootstrap_called);
    GDEX_EXPECT_TRUE(shutdown_called);
    gdextest::configure_host({});
}

GDEX_TEST(self, empty_host_config_is_a_no_op) {
    bootstrap_called = false;
    shutdown_called = false;
    gdextest::configure_host({});
    gdextest::bootstrap_host();
    gdextest::shutdown_host();
    GDEX_EXPECT_FALSE(bootstrap_called);
    GDEX_EXPECT_FALSE(shutdown_called);
}

// --- registry: filter matching -------------------------------------------
GDEX_TEST(self, filter_positive_glob_matches) {
    gdextest::Filter f;
    f.patterns = {"self.*"};
    auto sel = gdextest::TestRegistry::instance().select(f);
    bool has_self = false;
    for (auto *tc : sel) {
        if (std::string(tc->suite) == "self") has_self = true;
    }
    GDEX_EXPECT_TRUE(has_self);
}

GDEX_TEST(self, filter_negative_glob_excludes) {
    gdextest::Filter f;
    f.patterns = {"*", "-self.*"};
    auto sel = gdextest::TestRegistry::instance().select(f);
    for (auto *tc : sel) {
        GDEX_EXPECT_TRUE(std::string(tc->suite) != "self");
    }
}

GDEX_TEST(self, shard_k_of_n_is_disjoint_and_complete) {
    gdextest::Filter base;
    auto all = gdextest::TestRegistry::instance().select(base);
    size_t total = all.size();

    gdextest::Filter f;
    f.shard_count = 4;
    std::vector<std::string> seen;
    size_t acc = 0;
    for (int k = 0; k < 4; ++k) {
        f.shard_index = k;
        auto shard = gdextest::TestRegistry::instance().select(f);
        acc += shard.size();
        for (auto *tc : shard) {
            seen.emplace_back(std::string(tc->suite) + "." + tc->name);
        }
    }
    GDEX_EXPECT_EQ(acc, total);   // complete coverage
    std::sort(seen.begin(), seen.end());
    bool dup = false;
    for (size_t i = 1; i < seen.size(); ++i) if (seen[i] == seen[i - 1]) dup = true;
    GDEX_EXPECT_FALSE(dup);        // disjoint
}

// --- assertions: failures are recorded (not thrown) ----------------------
GDEX_TEST(self, expect_true_records_failure_and_continues) {
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDEX_EXPECT_TRUE(1 == 2);   // deliberately false
    });
    GDEX_EXPECT_EQ(n, 1);
}

GDEX_TEST(self, expect_eq_records_failure_and_formats_values) {
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDEX_EXPECT_EQ(1, 2);
    });
    GDEX_EXPECT_EQ(n, 1);
}

GDEX_TEST(self, multiple_failures_all_recorded) {
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDEX_EXPECT_TRUE(false);
        GDEX_EXPECT_EQ(1, 2);
        GDEX_EXPECT_FALSE(true);
    });
    GDEX_EXPECT_EQ(n, 3);
}

GDEX_TEST(self, passing_assertions_record_no_failures) {
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDEX_EXPECT(true);
        GDEX_EXPECT_TRUE(true);
        GDEX_EXPECT_FALSE(false);
        GDEX_EXPECT_EQ(2, 2);
        GDEX_EXPECT_NE(2, 3);
        GDEX_EXPECT_LT(1, 2);
        GDEX_EXPECT_LE(2, 2);
        GDEX_EXPECT_GT(2, 1);
        GDEX_EXPECT_GE(2, 2);
        GDEX_EXPECT_NEAR(1.0, 1.001, 0.01);
        GDEX_EXPECT_STR_EQ("same", "same");
        GDEX_EXPECT_STR_CONTAINS("hello world", "world");
        int value = 7;
        GDEX_EXPECT_NULL(nullptr);
        GDEX_EXPECT_NOT_NULL(&value);
    });
    GDEX_EXPECT_EQ(n, 0);
}

GDEX_TEST(self, assertion_macros_record_each_failure) {
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        int value = 7;
        GDEX_EXPECT(false);
        GDEX_EXPECT_TRUE(false);
        GDEX_EXPECT_FALSE(true);
        GDEX_EXPECT_EQ(1, 2);
        GDEX_EXPECT_NE(2, 2);
        GDEX_EXPECT_LT(2, 1);
        GDEX_EXPECT_LE(2, 1);
        GDEX_EXPECT_GT(1, 2);
        GDEX_EXPECT_GE(1, 2);
        GDEX_EXPECT_NEAR(1.0, 2.0, 0.01);
        GDEX_EXPECT_STR_EQ("left", "right");
        GDEX_EXPECT_STR_CONTAINS("hello", "missing");
        GDEX_EXPECT_NULL(&value);
        GDEX_EXPECT_NOT_NULL(nullptr);
        GDEX_FAIL("deliberate failure");
    });
    GDEX_EXPECT_EQ(n, 15);
}

GDEX_TEST(self, comparison_macros_evaluate_operands_once) {
    static int evaluations = 0;
    evaluations = 0;
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDEX_EXPECT_EQ(++evaluations, 2);
    });
    GDEX_EXPECT_EQ(n, 1);
    GDEX_EXPECT_EQ(evaluations, 1);
}

GDEX_TEST(self, abort_macro_records_failure_and_stops_body) {
    static bool reached_after_abort = false;
    reached_after_abort = false;
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDEX_ABORT_TEST("stop here");
        reached_after_abort = true;
    });
    GDEX_EXPECT_EQ(n, 1);
    GDEX_EXPECT_FALSE(reached_after_abort);
}

// --- skipping: GDEX_SKIP stops the body and is not a failure -----------------
GDEX_TEST(self, skip_stops_body_and_is_not_a_failure) {
    // A static local needs no capture, so the lambda below stays a plain function
    // pointer (run_sub_and_count_failures takes void(*)(TestContext&)).
    static bool reached_after_skip = false;
    reached_after_skip = false;
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDEX_SKIP("precondition not met");
        reached_after_skip = true;   // must never run
    });
    GDEX_EXPECT_EQ(n, 0);                  // a skip is not a failure
    GDEX_EXPECT_FALSE(reached_after_skip); // the body stopped at the skip
}

// --- teardown: registered callbacks run even on abort/skip -------------------
GDEX_TEST(self, teardowns_run_on_normal_completion) {
    static int teardown_calls = 0;
    teardown_calls = 0;
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        ctx.add_teardown([] { ++teardown_calls; });
        GDEX_EXPECT_TRUE(true);
    });
    GDEX_EXPECT_EQ(n, 0);
    GDEX_EXPECT_EQ(teardown_calls, 1);
}

GDEX_TEST(self, teardowns_run_when_body_aborts) {
    static int teardown_calls = 0;
    teardown_calls = 0;
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        ctx.add_teardown([] { ++teardown_calls; });
        GDEX_ABORT_TEST("stop here");
    });
    GDEX_EXPECT_EQ(n, 1);          // the abort is still a failure
    GDEX_EXPECT_EQ(teardown_calls, 1);   // ...and the teardown still ran
}

GDEX_TEST(self, teardowns_run_when_body_skips) {
    static int teardown_calls = 0;
    teardown_calls = 0;
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        ctx.add_teardown([] { ++teardown_calls; });
        GDEX_SKIP("precondition not met");
    });
    GDEX_EXPECT_EQ(n, 0);          // a skip is not a failure
    GDEX_EXPECT_EQ(teardown_calls, 1);   // the teardown still ran
}

GDEX_TEST(self, teardowns_run_in_reverse_registration_order) {
    static std::vector<std::string> order;
    order.clear();
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        ctx.add_teardown([] { order.push_back("first"); });
        ctx.add_teardown([] { order.push_back("second"); });
    });
    GDEX_EXPECT_EQ(n, 0);
    GDEX_EXPECT_EQ(order.size(), 2u);
    GDEX_EXPECT_STR_EQ(order[0], "second");   // LIFO: last registered runs first
    GDEX_EXPECT_STR_EQ(order[1], "first");
}

GDEX_TEST(self, throwing_teardown_fails_test_and_others_still_run) {
    static int teardown_calls = 0;
    teardown_calls = 0;
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        ctx.add_teardown([] { throw 42; });
        ctx.add_teardown([] { ++teardown_calls; });
    });
    GDEX_EXPECT_EQ(n, 1);                    // the throwing teardown is a failure
    GDEX_EXPECT_EQ(teardown_calls, 1);       // the remaining teardown still ran
}

// --- JSON output: the writer must emit the documented schema ---------------
// Each test runs a body through run_sub_and_write_json, reads the file back,
// and asserts on the raw JSON text. Paths resolve against the runner's cwd (the
// disposable fixture dir), so leftover files are harmless build output.

GDEX_TEST(self, json_reports_failing_test_with_failure_details) {
    const char *path = "gdextest_self_json_fail.json";
    int n = gdextest::run_sub_and_write_json([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDEX_EXPECT_EQ(1, 2);   // deliberately false
    }, path);
    GDEX_EXPECT_EQ(n, 1);
    const std::string json = read_file(path);
    std::remove(path);
    GDEX_EXPECT_STR_CONTAINS(json, "\"totals\":{\"pass\":0,\"fail\":1,\"skip\":0,\"crashed\":0}");
    GDEX_EXPECT_STR_CONTAINS(json, "\"status\":\"fail\"");
    GDEX_EXPECT_STR_CONTAINS(json, "\"failures\":[{\"file\":");
    GDEX_EXPECT_STR_CONTAINS(json, "\"line\":");
    GDEX_EXPECT_STR_CONTAINS(json, "\"message\":\"expected 1 == 2");
    GDEX_EXPECT_STR_CONTAINS(json, "\\n  expected: 1");  // multi-line message, JSON-escaped
}

GDEX_TEST(self, json_reports_passing_test_as_pass) {
    const char *path = "gdextest_self_json_pass.json";
    int n = gdextest::run_sub_and_write_json([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDEX_EXPECT_EQ(2, 2);
    }, path);
    GDEX_EXPECT_EQ(n, 0);
    const std::string json = read_file(path);
    std::remove(path);
    GDEX_EXPECT_STR_CONTAINS(json, "\"totals\":{\"pass\":1,\"fail\":0,\"skip\":0,\"crashed\":0}");
    GDEX_EXPECT_STR_CONTAINS(json, "\"status\":\"pass\"");
    GDEX_EXPECT_STR_CONTAINS(json, "\"failures\":[]");
}

GDEX_TEST(self, json_reports_skipped_test_with_reason) {
    const char *path = "gdextest_self_json_skip.json";
    int n = gdextest::run_sub_and_write_json([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDEX_SKIP("optional service missing");
    }, path);
    GDEX_EXPECT_EQ(n, 0);
    const std::string json = read_file(path);
    std::remove(path);
    GDEX_EXPECT_STR_CONTAINS(json, "\"totals\":{\"pass\":0,\"fail\":0,\"skip\":1,\"crashed\":0}");
    GDEX_EXPECT_STR_CONTAINS(json, "\"status\":\"skipped\"");
    GDEX_EXPECT_STR_CONTAINS(json, "\"reason\":\"optional service missing\"");
}

GDEX_TEST(self, json_escapes_quotes_and_newlines_in_messages) {
    const char *path = "gdextest_self_json_escape.json";
    int n = gdextest::run_sub_and_write_json([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDEX_FAIL("say \"hi\"\nnext line");
    }, path);
    GDEX_EXPECT_EQ(n, 1);
    const std::string json = read_file(path);
    std::remove(path);
    // The raw message must appear escaped: \" for the quote, \n for the newline.
    GDEX_EXPECT_STR_CONTAINS(json, "say \\\"hi\\\"\\nnext line");
}

// Tagged registration is exercised by both the synchronous and asynchronous
// variants. The registry tests below verify that explicit tags survive.
GDEX_TEST_T(self, tagged_sync_registration, TAG_UNIT | TAG_SLOW) {
    GDEX_EXPECT_TRUE(true);
}

GDEX_TEST_ASYNC_T(self, tagged_async_registration, TAG_ASYNC | TAG_SLOW) {
    GDEX_EXPECT_TRUE(true);
    co_return;
}

GDEX_TEST(self, tagged_registration_preserves_metadata) {
    const auto &cases = gdextest::TestRegistry::instance().all();
    bool found_sync = false;
    bool found_async = false;
    for (const auto &test_case : cases) {
        if (std::string(test_case.suite) != "self") continue;
        if (std::string(test_case.name) == "tagged_sync_registration") {
            found_sync = true;
            GDEX_EXPECT_TRUE(test_case.fn != nullptr);
            GDEX_EXPECT_EQ(test_case.async_fn, nullptr);
            GDEX_EXPECT_TRUE((test_case.tags & gdextest::TAG_UNIT) != 0);
            GDEX_EXPECT_TRUE((test_case.tags & gdextest::TAG_SLOW) != 0);
        }
        if (std::string(test_case.name) == "tagged_async_registration") {
            found_async = true;
            GDEX_EXPECT_EQ(test_case.fn, nullptr);
            GDEX_EXPECT_TRUE(test_case.async_fn != nullptr);
            GDEX_EXPECT_TRUE((test_case.tags & gdextest::TAG_ASYNC) != 0);
            GDEX_EXPECT_TRUE((test_case.tags & gdextest::TAG_SLOW) != 0);
        }
    }
    GDEX_EXPECT_TRUE(found_sync);
    GDEX_EXPECT_TRUE(found_async);
}

// --- async: the manual pump (plan §7.2) -----------------------------------
// SubAsyncPump simulates process_frame ticks and a monotonic ms clock, so the
// coroutine machinery (suspend/resume, per-wait timeout, isolate budget, JSON)
// is verifiable headlessly without a Godot engine.

namespace {
// Incremented once per simulated frame by the self-tests below.
int g_async_frame_counter = 0;
}

GDEX_TEST(self, async_await_frames_resumes_after_exact_ticks) {
    g_async_frame_counter = 0;
    gdextest::TestContext sub_ctx;
    gdextest::SubAsyncPump pump;
    bool pending = pump.start([](gdextest::TestContext &ctx) -> gdextest::Task {
        const int before = g_async_frame_counter;
        co_await ctx.await_frames(2);
        GDEX_EXPECT_EQ(g_async_frame_counter - before, 2);
        co_await ctx.await_frames(1);
        GDEX_EXPECT_EQ(g_async_frame_counter - before, 3);
        co_await ctx.await_frames(0);   // resolves immediately, consumes no frame
        GDEX_EXPECT_EQ(g_async_frame_counter - before, 3);
    }, sub_ctx);
    GDEX_EXPECT_TRUE(pending);
    int guard = 0;
    while (pending && ++guard <= 100) {
        ++g_async_frame_counter;   // one simulated frame elapsed
        pending = pump.step(16);
    }
    GDEX_EXPECT_FALSE(pending);
    GDEX_EXPECT_EQ(g_async_frame_counter, 3);
    GDEX_EXPECT_EQ(sub_ctx.failure_count(), 0);
}

GDEX_TEST(self, async_timer_resumes_after_elapsed_simulated_time) {
    gdextest::TestContext sub_ctx;
    gdextest::SubAsyncPump pump;
    bool pending = pump.start([](gdextest::TestContext &ctx) -> gdextest::Task {
        co_await ctx.await_timer_ms(50);
        GDEX_EXPECT_TRUE(true);   // reached only after the simulated timer elapsed
    }, sub_ctx);
    GDEX_EXPECT_TRUE(pending);
    int guard = 0;
    while (pending && ++guard <= 100) { pending = pump.step(16); }
    GDEX_EXPECT_FALSE(pending);
    GDEX_EXPECT_EQ(sub_ctx.failure_count(), 0);
}

GDEX_TEST(self, async_never_resolving_wait_fails_with_timeout) {
    gdextest::TestContext sub_ctx;
    gdextest::SubAsyncPump pump;
    bool pending = pump.start([](gdextest::TestContext &ctx) -> gdextest::Task {
        // A 60-second wait with a 50 ms deadline: the pump must fail the test
        // at the deadline instead of ever resuming the body.
        co_await ctx.await_timer_ms(60000, 50);
        GDEX_FAIL("unreachable: the wait resolved before its timeout");
    }, sub_ctx);
    GDEX_EXPECT_TRUE(pending);
    int guard = 0;
    while (pending && ++guard <= 100) { pending = pump.step(16); }
    GDEX_EXPECT_FALSE(pending);
    GDEX_EXPECT_EQ(sub_ctx.failure_count(), 1);
    GDEX_EXPECT_STR_CONTAINS(sub_ctx.failures()[0].message, "timed out");
    // The body must never have resumed past the await.
    GDEX_EXPECT_EQ(sub_ctx.failures()[0].message.find("unreachable"), std::string::npos);
}

GDEX_TEST(self, async_wait_without_driver_records_failure) {
    gdextest::TestContext sub_ctx;
    // Creating and resuming the task directly (no pump active) means co_await
    // sees no driver: it must record a failure and continue, not suspend forever.
    gdextest::Task task = [](gdextest::TestContext &ctx) -> gdextest::Task {
        co_await ctx.await_frames(2);
        GDEX_EXPECT_TRUE(true);   // still runs; the await recorded the failure
    }(sub_ctx);
    task.resume();
    GDEX_EXPECT_TRUE(task.done());
    GDEX_EXPECT_EQ(sub_ctx.failure_count(), 1);
    GDEX_EXPECT_STR_CONTAINS(sub_ctx.failures()[0].message, "outside an async test");
}

GDEX_TEST(self, async_isolate_timeout_fails_test) {
    gdextest::TestContext sub_ctx;
    gdextest::SubAsyncPump pump;
    bool pending = pump.start([](gdextest::TestContext &ctx) -> gdextest::Task {
        // Two 40 s waits: each is under the per-wait timeout, but together they
        // exceed the per-test isolate budget (kDefaultIsolateTimeoutSec = 60 s).
        co_await ctx.await_timer_ms(40000, 40000);
        co_await ctx.await_timer_ms(40000, 40000);
    }, sub_ctx);
    GDEX_EXPECT_TRUE(pending);
    // The first wait resolves at t = 40 s; the second would resolve at t = 80 s,
    // but the isolate budget fails the test at t = 60 s.
    int guard = 0;
    while (pending && ++guard <= 100) { pending = pump.step(20000); }
    GDEX_EXPECT_FALSE(pending);
    GDEX_EXPECT_EQ(sub_ctx.failure_count(), 1);
    GDEX_EXPECT_STR_CONTAINS(sub_ctx.failures()[0].message, "isolate");
}

GDEX_TEST(self, async_json_reports_timeout_as_fail) {
    const char *path = "gdextest_self_json_async_timeout.json";
    int n = gdextest::run_sub_async_write_json([](gdextest::TestContext &ctx) -> gdextest::Task {
        co_await ctx.await_timer_ms(60000, 50);
        GDEX_FAIL("unreachable");
    }, path);
    GDEX_EXPECT_EQ(n, 1);
    const std::string json = read_file(path);
    std::remove(path);
    GDEX_EXPECT_STR_CONTAINS(json, "\"totals\":{\"pass\":0,\"fail\":1,\"skip\":0,\"crashed\":0}");
    GDEX_EXPECT_STR_CONTAINS(json, "\"status\":\"fail\"");
    GDEX_EXPECT_STR_CONTAINS(json, "timed out");
}

#endif // GDEXTEST_ENABLED
