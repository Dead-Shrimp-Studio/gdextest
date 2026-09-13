---
title: Async tests
description: Multi-frame tests with co_await: waits, timeouts, and budgets.
order: 30
sidebar: Basics
draft: false
---

# Async tests

Some behavior only shows up across engine frames: a tween settling, a deferred call landing, a timer firing. Async tests suspend the body, let the engine run, and resume it later. The body is a C++20 coroutine; the runner drives it with a `SceneTree.process_frame` pump.

## Your first async test

```cpp
#include <cstdint>
#include <godot_cpp/classes/engine.hpp>
#include "gdextest/assert.h"
#include "gdextest/registry.h"

GDEX_TEST_ASYNC(async, engine_frames_advance_across_awaited_frames) {
    godot::Engine *engine = godot::Engine::get_singleton();
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(engine));
    const int64_t before = static_cast<int64_t>(engine->get_process_frames());
    co_await ctx.await_frames(2);
    const int64_t after = static_cast<int64_t>(engine->get_process_frames());
    GDEX_EXPECT_GE(after - before, 2);
}
```

`GDEX_TEST_ASYNC` registers a coroutine tagged `TAG_ASYNC`. Use `GDEX_TEST_ASYNC_T(suite, name, tags)` to add your own tags. The body must end with `co_return;`.

## Waits

| Wait | Resumes after | Notes |
| --- | --- | --- |
| `co_await ctx.await_frames(n)` | `n` `process_frame` ticks | `await_frames(0)` resolves immediately. |
| `co_await ctx.await_timer_ms(ms)` | at least `ms` milliseconds | Measured with the engine's millisecond clock. |

Both take an optional second argument, `timeout_ms`:

```cpp
co_await ctx.await_frames(5, 500);   // fail if not resumed within 500 ms
co_await ctx.await_timer_ms(100, 5000);
```

A `timeout_ms` of `0` means use the configured default:

- `await_frames` uses `timeout_ms` from `[gdextest.test]` in `.gdextest.toml` (default 30000).
- `await_timer_ms` uses the larger of the wait itself and that default. A 40-second timer with default budgets waits the full 40 seconds.

## Timeouts and budgets

Two safety nets bound every async test. A test that never resolves fails; it never hangs the run.

| Budget | Default | Config key | CLI flag |
| --- | --- | --- | --- |
| Per wait | 30000 ms | `[gdextest.test] timeout_ms` | `--gdextest-timeout-ms` |
| Per test (isolate) | 60 s | `[gdextest.test] isolate_timeout_sec` | `--gdextest-isolate-timeout-sec` |

- When a wait passes its deadline, the runner fails the test with a `timed out` failure and destroys the suspended coroutine. The body never resumes past that point.
- The isolate budget bounds the whole test. A chain of awaits that each fit under the per-wait timeout but together exceed the budget also fails. The message contains `isolate`.

The CLI forwards the TOML budgets on every run, so slow CI machines can raise them without rebuilding the framework.

## How the pump works

- The runner starts one async test and runs it to its first suspension.
- On suspension it connects a `process_frame` callback and returns control to the engine.
- Each frame advances the active wait and resumes the coroutine when the wait resolves.
- Async tests run **one at a time, in declaration order**. No two bodies interleave, so results stay deterministic.
- Exceptions in a coroutine body are captured and reported like sync failures. An abort (`GDEX_ABORT_TEST`) surfaces as status `crashed` for async tests.

## Rules and pitfalls

- **Use `co_return;`**, not `return;`. A coroutine rejects bare `return` at compile time.
- **`co_await` only inside async bodies.** A `co_await` in a plain `GDEX_TEST` records a failure (`used outside an async test run`) and continues; it does not suspend.
- **Await loops.** `while (...) { co_await ctx.await_frames(1); }` is legal. The isolate budget still bounds the total time.
- **Wall-clock durations vary.** `await_timer_ms(100)` resumes after at least 100 ms. Assert lower bounds, not exact values.
- **A timed-out wait is a failure, not a skip.** JSON reports status `fail` with a message containing `timed out`.

## Testing async machinery without an engine

The framework's own suite verifies the coroutine machinery headlessly with `SubAsyncPump` from `gdextest/runner.h`. It simulates frames and a millisecond clock, so timeouts and budgets are testable without a live engine. See the [API reference](/projects/gdextest/docs/api-reference) for its two methods, `start()` and `step()`.
