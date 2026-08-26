// Async / multi-frame test support (plan §7.2, Milestone C). Pure C++ core —
// no Godot types: the awaitables only *describe* what a suspended test is
// waiting for. The engine-boundary pump in runner.cpp interprets that request
// against the live SceneTree's `process_frame` signal; the self-test
// SubAsyncPump simulates frames with a fake clock.
#pragma once

#include <coroutine>
#include <exception>
#include <string>

#include "config.h"
#include "context.h"

namespace gdextest {

// --- Task: the coroutine type behind GDEX_TEST_ASYNC -------------------------
// A lazily-started coroutine: the body begins on the first resume() and runs
// until it co_awaits (suspending) or completes. Exceptions thrown by the body
// (GDEX_ABORT_TEST / GDEX_SKIP / crashes) are captured into the promise and
// surfaced through exception() after the task completes, so resume() never
// propagates out of the runner's frame.
class Task {
public:
    struct promise_type {
        Task get_return_object() noexcept {
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_void() noexcept {}
        void unhandled_exception() { exception = std::current_exception(); }
        std::exception_ptr exception;
    };

    using handle_type = std::coroutine_handle<promise_type>;

    Task() = default;
    explicit Task(handle_type handle) noexcept : handle_(handle) {}
    Task(const Task &) = delete;
    Task &operator=(const Task &) = delete;
    Task(Task &&other) noexcept : handle_(other.handle_) { other.handle_ = nullptr; }
    Task &operator=(Task &&other) noexcept {
        if (this != &other) {
            if (handle_) handle_.destroy();
            handle_ = other.handle_;
            other.handle_ = nullptr;
        }
        return *this;
    }
    ~Task() {
        if (handle_) handle_.destroy();
    }

    bool done() const { return handle_ && handle_.done(); }
    void resume() { handle_.resume(); }
    std::exception_ptr exception() const {
        return handle_ ? handle_.promise().exception : nullptr;
    }

private:
    handle_type handle_ = nullptr;
};

// --- Await coordination ------------------------------------------------------
enum class AwaitKind { Frames, TimerMs };

// What a suspended test is waiting for. `frames_left`/`duration_ms`/`timeout_ms`
// are set by the awaitable; `resume_at_ms`/`deadline_ms` are stamped by the pump
// driver (engine clock or simulated) once the suspension is observed.
struct AwaitRequest {
    AwaitKind kind = AwaitKind::Frames;
    int64_t frames_left = 0;
    int64_t duration_ms = 0;
    int64_t timeout_ms = 0;
    std::string description;    // human-readable, used in timeout messages
    int64_t resume_at_ms = -1;  // TimerMs: absolute time the wait resolves
    int64_t deadline_ms = -1;   // absolute time the wait is failed as a timeout
};

enum class AwaitStatus { Pending, Resolved, TimedOut };

// The single active suspension. Mirrors the runner's `g_active_ctx` pattern:
// the framework drives one test at a time, so one slot is enough.
class AsyncCoordinator {
public:
    static AsyncCoordinator &instance() {
        static AsyncCoordinator coordinator;
        return coordinator;
    }

    // Called by await_suspend when a body co_awaits.
    void suspend(std::coroutine_handle<> handle, AwaitRequest request) {
        current_ = handle;
        request_ = std::move(request);
    }

    bool has_pending() const { return current_ != nullptr; }
    std::coroutine_handle<> current() const { return current_; }
    const AwaitRequest &request() const { return request_; }

    // Converts the relative request into absolute times using the driver's clock.
    void stamp(int64_t now_ms) {
        if (request_.kind == AwaitKind::TimerMs) {
            request_.resume_at_ms = now_ms + request_.duration_ms;
        }
        request_.deadline_ms = now_ms + request_.timeout_ms;
    }

    // Advance one pump tick at `now_ms` (one engine process_frame, or one
    // simulated step). A wait that resolves wins over a coincident deadline.
    AwaitStatus advance(int64_t now_ms) {
        if (!current_) return AwaitStatus::Resolved;
        if (request_.kind == AwaitKind::Frames) {
            request_.frames_left -= 1;
            if (request_.frames_left <= 0) return AwaitStatus::Resolved;
        } else if (now_ms >= request_.resume_at_ms) {
            return AwaitStatus::Resolved;
        }
        if (now_ms >= request_.deadline_ms) return AwaitStatus::TimedOut;
        return AwaitStatus::Pending;
    }

    // True while a driver (engine pump or SubAsyncPump) is active. co_await
    // without one records a failure instead of suspending forever.
    bool driver_active() const { return driver_active_; }
    void set_driver_active(bool active) { driver_active_ = active; }

    void clear() {
        current_ = nullptr;
        request_ = AwaitRequest{};
    }

private:
    AsyncCoordinator() = default;
    std::coroutine_handle<> current_ = nullptr;
    AwaitRequest request_;
    bool driver_active_ = false;
};

// --- Awaitables ---------------------------------------------------------------
// Used as `co_await ctx.await_frames(2)` inside GDEX_TEST_ASYNC bodies.

class FrameAwaiter {
public:
    FrameAwaiter(TestContext &ctx, int64_t frames, int64_t timeout_ms)
        : ctx_(&ctx), frames_(frames), timeout_ms_(timeout_ms) {}

    bool await_ready() const noexcept { return frames_ <= 0; }
    bool await_suspend(std::coroutine_handle<> handle) {
        if (!AsyncCoordinator::instance().driver_active()) {
            ctx_->fail("", 0, "co_await ctx.await_frames(...) used outside an async test run (GDEX_TEST_ASYNC)");
            return false;  // don't suspend; the body continues with the failure recorded
        }
        AwaitRequest request;
        request.kind = AwaitKind::Frames;
        request.frames_left = frames_;
        request.timeout_ms = timeout_ms_;
        request.description = "await_frames(" + std::to_string(frames_) + ")";
        AsyncCoordinator::instance().suspend(handle, std::move(request));
        return true;
    }
    void await_resume() noexcept {}

private:
    TestContext *ctx_;
    int64_t frames_;
    int64_t timeout_ms_;
};

class TimerAwaiter {
public:
    TimerAwaiter(TestContext &ctx, int64_t ms, int64_t timeout_ms)
        : ctx_(&ctx), duration_ms_(ms), timeout_ms_(timeout_ms) {}

    bool await_ready() const noexcept { return duration_ms_ <= 0; }
    bool await_suspend(std::coroutine_handle<> handle) {
        if (!AsyncCoordinator::instance().driver_active()) {
            ctx_->fail("", 0, "co_await ctx.await_timer_ms(...) used outside an async test run (GDEX_TEST_ASYNC)");
            return false;
        }
        AwaitRequest request;
        request.kind = AwaitKind::TimerMs;
        request.duration_ms = duration_ms_;
        request.timeout_ms = timeout_ms_;
        request.description = "await_timer_ms(" + std::to_string(duration_ms_) + ")";
        AsyncCoordinator::instance().suspend(handle, std::move(request));
        return true;
    }
    void await_resume() noexcept {}

private:
    TestContext *ctx_;
    int64_t duration_ms_;
    int64_t timeout_ms_;
};

// --- TestContext::await_* (declared in context.h, defined here) ---------------
inline FrameAwaiter TestContext::await_frames(int64_t frames, int64_t timeout_ms) {
    return FrameAwaiter(*this, frames, timeout_ms);
}

inline TimerAwaiter TestContext::await_timer_ms(int64_t ms, int64_t timeout_ms) {
    // A timer's own duration is a legitimate wait; the timeout only guards
    // against waits that never resolve, so it defaults to at least the wait.
    if (timeout_ms <= 0) timeout_ms = ms > kDefaultTimeoutMs ? ms : kDefaultTimeoutMs;
    return TimerAwaiter(*this, ms, timeout_ms);
}

}  // namespace gdextest
