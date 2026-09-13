
#ifdef GDEXTEST_ENABLED

#include <cstdint>

#include <godot_cpp/classes/engine.hpp>
#include <godot_cpp/classes/time.hpp>

#include "gdextest/assert.h"
#include "gdextest/async.h"
#include "gdextest/engine.h"
#include "gdextest/registry.h"

// The engine's process frame counter advances across an awaited frame pause:
// await_frames(2) must observe at least two new engine frames before resuming.
GDEX_TEST_ASYNC(async, engine_frames_advance_across_awaited_frames) {
    godot::Engine *engine = godot::Engine::get_singleton();
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(engine));
    const int64_t before = static_cast<int64_t>(engine->get_process_frames());
    co_await ctx.await_frames(2);
    const int64_t after = static_cast<int64_t>(engine->get_process_frames());
    GDEX_EXPECT_GE(after - before, 2);
}

// Two sequential frame awaits accumulate: each await observes at least one new
// frame, and the body can interleave assertions with awaits.
GDEX_TEST_ASYNC(async, sequential_frame_awaits_accumulate) {
    godot::Engine *engine = godot::Engine::get_singleton();
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(engine));
    const int64_t before = static_cast<int64_t>(engine->get_process_frames());
    co_await ctx.await_frames(1);
    const int64_t mid = static_cast<int64_t>(engine->get_process_frames());
    co_await ctx.await_frames(1);
    const int64_t after = static_cast<int64_t>(engine->get_process_frames());
    GDEX_EXPECT_GE(mid - before, 1);
    GDEX_EXPECT_GE(after - mid, 1);
}

// A timed await resumes after roughly the requested wall-clock duration.
GDEX_TEST_ASYNC(async, timer_await_resumes_after_elapsed_time) {
    godot::Time *time = godot::Time::get_singleton();
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(time));
    const int64_t before = static_cast<int64_t>(time->get_ticks_msec());
    co_await ctx.await_timer_ms(100);
    const int64_t after = static_cast<int64_t>(time->get_ticks_msec());
    GDEX_EXPECT_GE(after - before, 100);
}

#endif // GDEXTEST_ENABLED
