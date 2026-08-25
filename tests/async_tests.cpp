// Async / multi-frame suite (plan §12 "async", Milestone C).
//
// These tests exercise the live engine's frame loop: each body suspends on a
// co_await and the runner's process_frame pump resumes it across frames. They
// only run through the engine trigger (the fixture's EditorPlugin), where the
// runner attaches the live tree node to each test's context.
//
// The timeout/isolate machinery (a wait that never resolves is failed, never
// hangs the run) is verified headlessly in framework_self_tests.cpp via the
// manual SubAsyncPump; these tests verify the real engine path.
#ifdef GDEXTEST_ENABLED

#include <cstdint>

#include <godot_cpp/classes/engine.hpp>
#include <godot_cpp/classes/time.hpp>

#include "framework/assert.h"
#include "framework/async.h"
#include "framework/engine.h"
#include "framework/registry.h"

// The engine's process frame counter advances across an awaited frame pause:
// await_frames(2) must observe at least two new engine frames before resuming.
GDX_TEST_ASYNC(async, engine_frames_advance_across_awaited_frames) {
    godot::Engine *engine = godot::Engine::get_singleton();
    GDX_EXPECT_NOT_NULL(static_cast<void *>(engine));
    const int64_t before = static_cast<int64_t>(engine->get_process_frames());
    co_await ctx.await_frames(2);
    const int64_t after = static_cast<int64_t>(engine->get_process_frames());
    GDX_EXPECT_GE(after - before, 2);
}

// Two sequential frame awaits accumulate: each await observes at least one new
// frame, and the body can interleave assertions with awaits.
GDX_TEST_ASYNC(async, sequential_frame_awaits_accumulate) {
    godot::Engine *engine = godot::Engine::get_singleton();
    GDX_EXPECT_NOT_NULL(static_cast<void *>(engine));
    const int64_t before = static_cast<int64_t>(engine->get_process_frames());
    co_await ctx.await_frames(1);
    const int64_t mid = static_cast<int64_t>(engine->get_process_frames());
    co_await ctx.await_frames(1);
    const int64_t after = static_cast<int64_t>(engine->get_process_frames());
    GDX_EXPECT_GE(mid - before, 1);
    GDX_EXPECT_GE(after - mid, 1);
}

// A timed await resumes after roughly the requested wall-clock duration.
GDX_TEST_ASYNC(async, timer_await_resumes_after_elapsed_time) {
    godot::Time *time = godot::Time::get_singleton();
    GDX_EXPECT_NOT_NULL(static_cast<void *>(time));
    const int64_t before = static_cast<int64_t>(time->get_ticks_msec());
    co_await ctx.await_timer_ms(100);
    const int64_t after = static_cast<int64_t>(time->get_ticks_msec());
    GDX_EXPECT_GE(after - before, 100);
}

#endif // GDEXTEST_ENABLED
