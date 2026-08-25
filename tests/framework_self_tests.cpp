// Framework self-tests (plan §12, category "self"). Verifies the framework's own
// behavior before any host code trusts it. Compiled only under GDEXTEST_ENABLED.
#ifdef GDEXTEST_ENABLED

#include <algorithm>
#include <cstdio>   // std::remove
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

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

GDX_TEST(self, host_config_invokes_portable_callbacks) {
    bootstrap_called = false;
    shutdown_called = false;
    gdextest::configure_host({&mark_bootstrap, &mark_shutdown});
    gdextest::bootstrap_host();
    gdextest::shutdown_host();
    GDX_EXPECT_TRUE(bootstrap_called);
    GDX_EXPECT_TRUE(shutdown_called);
    gdextest::configure_host({});
}

GDX_TEST(self, empty_host_config_is_a_no_op) {
    bootstrap_called = false;
    shutdown_called = false;
    gdextest::configure_host({});
    gdextest::bootstrap_host();
    gdextest::shutdown_host();
    GDX_EXPECT_FALSE(bootstrap_called);
    GDX_EXPECT_FALSE(shutdown_called);
}

// --- registry: filter matching -------------------------------------------
GDX_TEST(self, filter_positive_glob_matches) {
    gdextest::Filter f;
    f.patterns = {"self.*"};
    auto sel = gdextest::TestRegistry::instance().select(f);
    bool has_self = false;
    for (auto *tc : sel) {
        if (std::string(tc->suite) == "self") has_self = true;
    }
    GDX_EXPECT_TRUE(has_self);
}

GDX_TEST(self, filter_negative_glob_excludes) {
    gdextest::Filter f;
    f.patterns = {"*", "-self.*"};
    auto sel = gdextest::TestRegistry::instance().select(f);
    for (auto *tc : sel) {
        GDX_EXPECT_TRUE(std::string(tc->suite) != "self");
    }
}

GDX_TEST(self, shard_k_of_n_is_disjoint_and_complete) {
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
    GDX_EXPECT_EQ(acc, total);   // complete coverage
    std::sort(seen.begin(), seen.end());
    bool dup = false;
    for (size_t i = 1; i < seen.size(); ++i) if (seen[i] == seen[i - 1]) dup = true;
    GDX_EXPECT_FALSE(dup);        // disjoint
}

// --- assertions: failures are recorded (not thrown) ----------------------
GDX_TEST(self, expect_true_records_failure_and_continues) {
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDX_EXPECT_TRUE(1 == 2);   // deliberately false
    });
    GDX_EXPECT_EQ(n, 1);
}

GDX_TEST(self, expect_eq_records_failure_and_formats_values) {
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDX_EXPECT_EQ(1, 2);
    });
    GDX_EXPECT_EQ(n, 1);
}

GDX_TEST(self, multiple_failures_all_recorded) {
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDX_EXPECT_TRUE(false);
        GDX_EXPECT_EQ(1, 2);
        GDX_EXPECT_FALSE(true);
    });
    GDX_EXPECT_EQ(n, 3);
}

GDX_TEST(self, passing_assertions_record_no_failures) {
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDX_EXPECT_TRUE(true);
        GDX_EXPECT_EQ(2, 2);
        GDX_EXPECT_FALSE(false);
    });
    GDX_EXPECT_EQ(n, 0);
}

// --- skipping: GDX_SKIP stops the body and is not a failure -----------------
GDX_TEST(self, skip_stops_body_and_is_not_a_failure) {
    // A static local needs no capture, so the lambda below stays a plain function
    // pointer (run_sub_and_count_failures takes void(*)(TestContext&)).
    static bool reached_after_skip = false;
    reached_after_skip = false;
    int n = gdextest::run_sub_and_count_failures([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDX_SKIP("precondition not met");
        reached_after_skip = true;   // must never run
    });
    GDX_EXPECT_EQ(n, 0);                  // a skip is not a failure
    GDX_EXPECT_FALSE(reached_after_skip); // the body stopped at the skip
}

// --- JSON output: the writer must emit the documented schema ---------------
// Each test runs a body through run_sub_and_write_json, reads the file back,
// and asserts on the raw JSON text. Paths resolve against the runner's cwd (the
// disposable fixture dir), so leftover files are harmless build output.

GDX_TEST(self, json_reports_failing_test_with_failure_details) {
    const char *path = "gdextest_self_json_fail.json";
    int n = gdextest::run_sub_and_write_json([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDX_EXPECT_EQ(1, 2);   // deliberately false
    }, path);
    GDX_EXPECT_EQ(n, 1);
    const std::string json = read_file(path);
    std::remove(path);
    GDX_EXPECT_STR_CONTAINS(json, "\"totals\":{\"pass\":0,\"fail\":1,\"skip\":0,\"crashed\":0}");
    GDX_EXPECT_STR_CONTAINS(json, "\"status\":\"fail\"");
    GDX_EXPECT_STR_CONTAINS(json, "\"failures\":[{\"file\":");
    GDX_EXPECT_STR_CONTAINS(json, "\"line\":");
    GDX_EXPECT_STR_CONTAINS(json, "\"message\":\"expected 1 == 2");
    GDX_EXPECT_STR_CONTAINS(json, "\\n  expected: 1");  // multi-line message, JSON-escaped
}

GDX_TEST(self, json_reports_passing_test_as_pass) {
    const char *path = "gdextest_self_json_pass.json";
    int n = gdextest::run_sub_and_write_json([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDX_EXPECT_EQ(2, 2);
    }, path);
    GDX_EXPECT_EQ(n, 0);
    const std::string json = read_file(path);
    std::remove(path);
    GDX_EXPECT_STR_CONTAINS(json, "\"totals\":{\"pass\":1,\"fail\":0,\"skip\":0,\"crashed\":0}");
    GDX_EXPECT_STR_CONTAINS(json, "\"status\":\"pass\"");
    GDX_EXPECT_STR_CONTAINS(json, "\"failures\":[]");
}

GDX_TEST(self, json_reports_skipped_test_with_reason) {
    const char *path = "gdextest_self_json_skip.json";
    int n = gdextest::run_sub_and_write_json([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDX_SKIP("optional service missing");
    }, path);
    GDX_EXPECT_EQ(n, 0);
    const std::string json = read_file(path);
    std::remove(path);
    GDX_EXPECT_STR_CONTAINS(json, "\"totals\":{\"pass\":0,\"fail\":0,\"skip\":1,\"crashed\":0}");
    GDX_EXPECT_STR_CONTAINS(json, "\"status\":\"skipped\"");
    GDX_EXPECT_STR_CONTAINS(json, "\"reason\":\"optional service missing\"");
}

GDX_TEST(self, json_escapes_quotes_and_newlines_in_messages) {
    const char *path = "gdextest_self_json_escape.json";
    int n = gdextest::run_sub_and_write_json([](gdextest::TestContext &ctx) {
        (void)ctx;
        GDX_FAIL("say \"hi\"\nnext line");
    }, path);
    GDX_EXPECT_EQ(n, 1);
    const std::string json = read_file(path);
    std::remove(path);
    // The raw message must appear escaped: \" for the quote, \n for the newline.
    GDX_EXPECT_STR_CONTAINS(json, "say \\\"hi\\\"\\nnext line");
}

// --- async: the manual pump (plan §7.2) -----------------------------------
// SubAsyncPump simulates process_frame ticks and a monotonic ms clock, so the
// coroutine machinery (suspend/resume, per-wait timeout, isolate budget, JSON)
// is verifiable headlessly without a Godot engine.

namespace {
// Incremented once per simulated frame by the self-tests below.
int g_async_frame_counter = 0;
}

GDX_TEST(self, async_await_frames_resumes_after_exact_ticks) {
    g_async_frame_counter = 0;
    gdextest::TestContext sub_ctx;
    gdextest::SubAsyncPump pump;
    bool pending = pump.start([](gdextest::TestContext &ctx) -> gdextest::Task {
        const int before = g_async_frame_counter;
        co_await ctx.await_frames(2);
        GDX_EXPECT_EQ(g_async_frame_counter - before, 2);
        co_await ctx.await_frames(1);
        GDX_EXPECT_EQ(g_async_frame_counter - before, 3);
        co_await ctx.await_frames(0);   // resolves immediately, consumes no frame
        GDX_EXPECT_EQ(g_async_frame_counter - before, 3);
    }, sub_ctx);
    GDX_EXPECT_TRUE(pending);
    int guard = 0;
    while (pending && ++guard <= 100) {
        ++g_async_frame_counter;   // one simulated frame elapsed
        pending = pump.step(16);
    }
    GDX_EXPECT_FALSE(pending);
    GDX_EXPECT_EQ(g_async_frame_counter, 3);
    GDX_EXPECT_EQ(sub_ctx.failure_count(), 0);
}

GDX_TEST(self, async_timer_resumes_after_elapsed_simulated_time) {
    gdextest::TestContext sub_ctx;
    gdextest::SubAsyncPump pump;
    bool pending = pump.start([](gdextest::TestContext &ctx) -> gdextest::Task {
        co_await ctx.await_timer_ms(50);
        GDX_EXPECT_TRUE(true);   // reached only after the simulated timer elapsed
    }, sub_ctx);
    GDX_EXPECT_TRUE(pending);
    int guard = 0;
    while (pending && ++guard <= 100) { pending = pump.step(16); }
    GDX_EXPECT_FALSE(pending);
    GDX_EXPECT_EQ(sub_ctx.failure_count(), 0);
}

GDX_TEST(self, async_never_resolving_wait_fails_with_timeout) {
    gdextest::TestContext sub_ctx;
    gdextest::SubAsyncPump pump;
    bool pending = pump.start([](gdextest::TestContext &ctx) -> gdextest::Task {
        // A 60-second wait with a 50 ms deadline: the pump must fail the test
        // at the deadline instead of ever resuming the body.
        co_await ctx.await_timer_ms(60000, 50);
        GDX_FAIL("unreachable: the wait resolved before its timeout");
    }, sub_ctx);
    GDX_EXPECT_TRUE(pending);
    int guard = 0;
    while (pending && ++guard <= 100) { pending = pump.step(16); }
    GDX_EXPECT_FALSE(pending);
    GDX_EXPECT_EQ(sub_ctx.failure_count(), 1);
    GDX_EXPECT_STR_CONTAINS(sub_ctx.failures()[0].message, "timed out");
    // The body must never have resumed past the await.
    GDX_EXPECT_EQ(sub_ctx.failures()[0].message.find("unreachable"), std::string::npos);
}

GDX_TEST(self, async_wait_without_driver_records_failure) {
    gdextest::TestContext sub_ctx;
    // Creating and resuming the task directly (no pump active) means co_await
    // sees no driver: it must record a failure and continue, not suspend forever.
    gdextest::Task task = [](gdextest::TestContext &ctx) -> gdextest::Task {
        co_await ctx.await_frames(2);
        GDX_EXPECT_TRUE(true);   // still runs; the await recorded the failure
    }(sub_ctx);
    task.resume();
    GDX_EXPECT_TRUE(task.done());
    GDX_EXPECT_EQ(sub_ctx.failure_count(), 1);
    GDX_EXPECT_STR_CONTAINS(sub_ctx.failures()[0].message, "outside an async test");
}

GDX_TEST(self, async_isolate_timeout_fails_test) {
    gdextest::TestContext sub_ctx;
    gdextest::SubAsyncPump pump;
    bool pending = pump.start([](gdextest::TestContext &ctx) -> gdextest::Task {
        // Two 40 s waits: each is under the per-wait timeout, but together they
        // exceed the per-test isolate budget (kDefaultIsolateTimeoutSec = 60 s).
        co_await ctx.await_timer_ms(40000, 40000);
        co_await ctx.await_timer_ms(40000, 40000);
    }, sub_ctx);
    GDX_EXPECT_TRUE(pending);
    // The first wait resolves at t = 40 s; the second would resolve at t = 80 s,
    // but the isolate budget fails the test at t = 60 s.
    int guard = 0;
    while (pending && ++guard <= 100) { pending = pump.step(20000); }
    GDX_EXPECT_FALSE(pending);
    GDX_EXPECT_EQ(sub_ctx.failure_count(), 1);
    GDX_EXPECT_STR_CONTAINS(sub_ctx.failures()[0].message, "isolate");
}

GDX_TEST(self, async_json_reports_timeout_as_fail) {
    const char *path = "gdextest_self_json_async_timeout.json";
    int n = gdextest::run_sub_async_write_json([](gdextest::TestContext &ctx) -> gdextest::Task {
        co_await ctx.await_timer_ms(60000, 50);
        GDX_FAIL("unreachable");
    }, path);
    GDX_EXPECT_EQ(n, 1);
    const std::string json = read_file(path);
    std::remove(path);
    GDX_EXPECT_STR_CONTAINS(json, "\"totals\":{\"pass\":0,\"fail\":1,\"skip\":0,\"crashed\":0}");
    GDX_EXPECT_STR_CONTAINS(json, "\"status\":\"fail\"");
    GDX_EXPECT_STR_CONTAINS(json, "timed out");
}

#endif // GDEXTEST_ENABLED
