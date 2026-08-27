// Runner: the Godot-facing test execution boundary.
#pragma once

#include <functional>

#include "async.h"
#include "context.h"
#include "host.h"

#if defined(_WIN32)
#define GDEXTEST_API __declspec(dllexport)
#elif defined(gdextest_BUILDING)
#define GDEXTEST_API __attribute__((visibility("default")))
#else
#define GDEXTEST_API
#endif

namespace gdextest {

GDEXTEST_API void run_all_and_quit(void *tree_node);
GDEXTEST_API int run_sub_and_count_failures(void (*body)(TestContext &));

// Run a single test body with a fresh TestContext and write its result as a
// single-entry JSON document to `path` (same schema as --gdextest-json).
// Returns the body's failure count. Used by the self-test suite to verify the
// JSON writer without a full engine run.
GDEXTEST_API int run_sub_and_write_json(void (*body)(TestContext &), const char *path);

// Manual frame pump for async self-tests (plan §7.2): simulates process_frame
// ticks and a monotonic ms clock, so the coroutine machinery (suspend/resume,
// per-wait timeout, isolate budget) is verifiable without an engine.
class SubAsyncPump {
public:
    // Start an async body on a fresh simulated clock (t = 0). Returns true if
    // the body suspended (call step() to advance), false if it completed at once.
    bool start(std::function<Task(TestContext &)> body, TestContext &ctx);

    // Advance one simulated frame and `tick_ms` of simulated time. Returns true
    // while the body is still pending; false once it completed or was failed
    // (per-wait timeout / isolate budget).
    bool step(int64_t tick_ms = 16);

private:
    void finish();
    Task task_;
    TestContext *ctx_ = nullptr;
    int64_t now_ms_ = 0;
    int64_t test_start_ms_ = 0;
};

// Drive an async body to completion through the manual pump and write its result
// as a single-entry JSON document to `path` (same schema as --gdextest-json).
// Returns the body's failure count.
GDEXTEST_API int run_sub_async_write_json(std::function<Task(TestContext &)> body,
                                           const char *path);

} // namespace gdextest
