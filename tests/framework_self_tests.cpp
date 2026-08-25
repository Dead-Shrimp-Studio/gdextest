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

#endif // GDEXTEST_ENABLED
