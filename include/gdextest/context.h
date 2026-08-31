// Per-test result sink + owned-object tracking (plan §5.2). Pure C++ core.
#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "config.h"   // runtime_config() (default await timeout, isolate budget)

namespace gdextest {

class SignalMonitor;
using Teardown = std::function<void()>;

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

    // Register a live Godot Object or RefCounted handle for teardown checks.
    // The pointer is intentionally opaque here; implementation lives at the
    // engine boundary in runner.cpp.
    void track_object(void *obj);
    void track_ref(void *ref);

    // Register a cleanup callback the runner invokes when the test body ends —
    // including on GDEX_ABORT_TEST / throws / skips — so suites that create
    // temp files, sessions, or services are safe to abort at any point.
    // Teardowns run in reverse registration order (LIFO), before the
    // tracked-object/ref leak checks. A throwing teardown is caught and
    // reported as a test failure; remaining teardowns still run.
    void add_teardown(Teardown teardown) { teardowns_.push_back(std::move(teardown)); }

    const std::vector<Teardown> &teardowns() const { return teardowns_; }

    const std::vector<std::string> &resource_failures() const { return resource_failures_; }

    // Live engine access for integration tests. The handle is opaque here so the
    // core stays free of Godot types; engine-boundary accessors live in
    // gdextest/engine.h and cast this handle to the real Node/SceneTree.
    // Non-null only when the test runs through the real engine trigger.
    void set_engine(void *engine) { engine_ = engine; }
    void *engine_handle() const { return engine_; }

    SignalMonitor &signals();

    // Async waits for multi-frame tests (plan §7.2, Milestone C). Used as
    // `co_await ctx.await_frames(2)` inside a GDEX_TEST_ASYNC body; the runner's
    // frame pump resumes the body once the wait resolves. `timeout_ms` bounds
    // how long the wait may take before the test is failed (a safety net for
    // waits that never resolve). 0 means "use the configured default"
    // (runtime_config().timeout_ms). Implemented in async.h.
    FrameAwaiter await_frames(int64_t frames, int64_t timeout_ms = 0);
    TimerAwaiter await_timer_ms(int64_t ms, int64_t timeout_ms = 0);

private:
    std::vector<Failure> failures_;
    bool skipped_ = false;
    std::string skip_reason_;
    std::vector<Teardown> teardowns_;

    // Live engine host (the tree node handed to run_all_and_quit), or null for
    // self/sub invocations.
    void *engine_ = nullptr;
    SignalMonitor* signals_ = nullptr;

    struct TrackedObject { uint64_t id = 0; };
    struct TrackedRef { void *ptr = nullptr; int32_t initial_count = 0; };
    std::vector<TrackedObject> tracked_objects_;
    std::vector<TrackedRef> tracked_refs_;
    std::vector<std::string> resource_failures_;

public:
    const std::vector<TrackedObject> &tracked_objects() const { return tracked_objects_; }
    const std::vector<TrackedRef> &tracked_refs() const { return tracked_refs_; }
};

} // namespace gdextest
