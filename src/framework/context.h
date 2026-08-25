// Per-test result sink + owned-object tracking (plan §5.2). Pure C++ core.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "config.h"   // kDefaultTimeoutMs (default await timeout)

namespace gdextest {

struct Failure {
    std::string file;
    int line = 0;
    std::string message;
};

// Awaitables returned by TestContext::await_* (defined in async.h). Forward
// declarations keep context.h free of the coroutine machinery.
class FrameAwaiter;
class TimerAwaiter;

class TestContext {
public:
    // Called by assertion macros (plan §5.2). Recorded, never thrown.
    void fail(const char *file, int line, std::string message) {
        failures_.push_back({file ? file : "", line, std::move(message)});
    }

    bool ok() const { return failures_.empty(); }
    int failure_count() const { return static_cast<int>(failures_.size()); }
    const std::vector<Failure> &failures() const { return failures_; }

    // Throw to abort the current test only (caught inside the runner's frame —
    // never crosses an engine callback boundary; plan §5.2). Throws only when
    // GDEXTEST_ENABLED is active; otherwise a no-op.
    [[noreturn]] static void abort_test(const char *file, int line, std::string message);

    // Mark the current test as skipped for a runtime reason (timing, missing
    // fixture/service, unmet precondition) and stop the body. A skipped test never
    // counts as a pass or a failure; it appears in the human/JSON `skip` totals.
    // Implemented like abort_test: records on the active context, then throws a
    // private exception type caught inside the runner's own frame.
    [[noreturn]] static void skip(const char *file, int line, std::string reason);

    bool skipped() const { return skipped_; }
    const std::string &skip_reason() const { return skip_reason_; }

    // Live engine access for integration tests. The handle is opaque here so the
    // core stays free of Godot types; engine-boundary accessors live in
    // framework/engine.h and cast this handle to the real Node/SceneTree.
    // Non-null only when the test runs through the real engine trigger.
    void set_engine(void *engine) { engine_ = engine; }
    void *engine_handle() const { return engine_; }

    // Async waits for multi-frame tests (plan §7.2, Milestone C). Used as
    // `co_await ctx.await_frames(2)` inside a GDX_TEST_ASYNC body; the runner's
    // frame pump resumes the body once the wait resolves. `timeout_ms` bounds
    // how long the wait may take before the test is failed (a safety net for
    // waits that never resolve). Implemented in async.h.
    FrameAwaiter await_frames(int64_t frames, int64_t timeout_ms = kDefaultTimeoutMs);
    TimerAwaiter await_timer_ms(int64_t ms, int64_t timeout_ms = 0);

private:
    std::vector<Failure> failures_;
    bool skipped_ = false;
    std::string skip_reason_;

    // Live engine host (the tree node handed to run_all_and_quit), or null for
    // self/sub invocations.
    void *engine_ = nullptr;

    // Owned-object tracking (leak/UAF hooks; full impl lands at M4 per plan §7.4).
    // Declared now so the assertion macros can reference ctx.track_* without #ifdef churn.
public:
    void track_object(void * /*obj*/) { /* M4 */ }
    void track_ref(void * /*ref*/) { /* M4 */ }
};

} // namespace gdextest
