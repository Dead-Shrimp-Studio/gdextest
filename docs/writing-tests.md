---
title: Writing tests
description: Registration macros, tags, every assertion, teardowns, skipping, and resource tracking.
order: 20
sidebar: Basics
draft: false
---

# Writing tests

This page covers everything a test author needs: registration, tags, assertions, the test context, teardowns, skipping, and resource tracking. For the raw declarations, see the [API reference](/projects/gdextest/docs/api-reference).

## A test in one minute

```cpp
#include "gdextest/assert.h"
#include "gdextest/registry.h"
#include "my_extension/math_utils.h"   // your code under test

GDEX_TEST(math_utils, clamp_keeps_value_in_range) {
    GDEX_EXPECT_EQ(clamp(5, 0, 10), 5);
    GDEX_EXPECT_EQ(clamp(-1, 0, 10), 0);
    GDEX_EXPECT_EQ(clamp(42, 0, 10), 10);
}
```

The macro declares a function, registers it in a static registry, and opens the body. The body receives a `TestContext&` named `ctx`. Assertion macros reference `ctx` by that name, so it must stay in scope under that name inside `GDEX_TEST` bodies.

A failing expectation records a failure and **continues**. One test reports every failing check, not just the first.

## Registration macros

| Macro | Body kind | Default tag |
| --- | --- | --- |
| `GDEX_TEST(suite, name)` | plain function | `TAG_UNIT` |
| `GDEX_TEST_T(suite, name, tags)` | plain function | your tags |
| `GDEX_TEST_ASYNC(suite, name)` | C++20 coroutine | `TAG_ASYNC` |
| `GDEX_TEST_ASYNC_T(suite, name, tags)` | C++20 coroutine | your tags |

Rules:

- `suite` and `name` must be C++ identifiers. The runner displays and filters them as `suite.name`.
- Registration happens at static-initialization time, before the engine touches anything. No Godot objects take part in it.
- Coroutine bodies must end with `co_return;`. A bare `return;` does not compile inside a coroutine. See [Async tests](/projects/gdextest/docs/async-tests).

## Tags

Tags are bitmask metadata on each test. Pass any combination with `GDEX_TEST_T`:

| Tag | Meaning |
| --- | --- |
| `TAG_UNIT` | Pure-logic test. Default for `GDEX_TEST`. |
| `TAG_INTEGRATION` | Uses the live engine. Pair with `gdextest/engine.h`. |
| `TAG_ASYNC` | Coroutine body. Default for `GDEX_TEST_ASYNC`. |
| `TAG_SLOW` | Long-running test. Mark it so you can filter it out locally. |
| `TAG_FLAKY` | Known-flaky test. The runner retries it up to `flaky_retries` times (default 3). |

```cpp
GDEX_TEST_T(self, flaky_test_passes_after_retries, TAG_UNIT | TAG_FLAKY) {
    // ...
}
```

Bare tag names resolve inside the macros no matter what namespace your file uses. The CLI has no tag flag; tag-based selection is available through the `Filter` API (see the [API reference](/projects/gdextest/docs/api-reference)). `TAG_FLAKY` is the one tag the runner acts on by itself.

## The test context

Every body gets one fresh `TestContext` named `ctx`:

```cpp
GDEX_TEST_T(engine, tracked_object_is_clean_after_free, TAG_INTEGRATION) {
    godot::Node *child = memnew(godot::Node);
    ctx.track_object(child);                       // register for the leak check
    const uint64_t id = child->get_instance_id();
    memdelete(child);
    GDEX_EXPECT_NULL(godot::UtilityFunctions::instance_from_id(static_cast<int64_t>(id)));
}
```

Main uses:

| Call | Purpose |
| --- | --- |
| `ctx.add_teardown(fn)` | Register a cleanup callback. Runs LIFO when the body ends, even on abort or skip. |
| `ctx.track_object(ptr)` | Fail the test if this Godot `Object` is still alive at teardown. |
| `ctx.track_ref(ptr)` | Fail the test if this `RefCounted` gains references. |
| `ctx.signals()` | Get the per-test `SignalMonitor` (engine tests only). See [Engine integration](/projects/gdextest/docs/engine-integration). |
| `ctx.await_frames(n)` / `ctx.await_timer_ms(ms)` | Coroutine waits in async bodies. See [Async tests](/projects/gdextest/docs/async-tests). |

The context also exposes `failures()`, `failure_count()`, `skipped()`, and `skip_reason()` for inspection. The full member list lives in the [API reference](/projects/gdextest/docs/api-reference).

## Assertions

Header: `gdextest/assert.h`. Every macro is a statement; each one records its result on `ctx`.

### Expectations (non-fatal)

A failed expectation records a failure and the body continues.

| Macro | Passes when |
| --- | --- |
| `GDEX_EXPECT(cond)` | `cond` is truthy |
| `GDEX_EXPECT_TRUE(cond)` | alias of `GDEX_EXPECT` |
| `GDEX_EXPECT_FALSE(cond)` | `cond` is falsy |
| `GDEX_EXPECT_EQ(a, b)` | `a == b` |
| `GDEX_EXPECT_NE(a, b)` | `a != b` |
| `GDEX_EXPECT_LT(a, b)` | `a < b` |
| `GDEX_EXPECT_LE(a, b)` | `a <= b` |
| `GDEX_EXPECT_GT(a, b)` | `a > b` |
| `GDEX_EXPECT_GE(a, b)` | `a >= b` |
| `GDEX_EXPECT_NEAR(a, b, eps)` | absolute difference of `a` and `b` is at most `eps` (compared as `double`) |
| `GDEX_EXPECT_NULL(p)` | `p == nullptr` |
| `GDEX_EXPECT_NOT_NULL(p)` | `p != nullptr` |

### Fatal assertions

A fatal assertion records the failure and **stops the test** at that point. Use it when continuing makes no sense, for example when a needed pointer is null.

| Macro | Passes when |
| --- | --- |
| `GDEX_ASSERT_TRUE(cond)` | `cond` is truthy |
| `GDEX_ASSERT_FALSE(cond)` | `cond` is falsy |
| `GDEX_ASSERT_EQ(a, b)` | `a == b` |
| `GDEX_ASSERT_NE(a, b)` | `a != b` |
| `GDEX_ASSERT_NULL(p)` | `p == nullptr` |
| `GDEX_ASSERT_NOT_NULL(p)` | `p != nullptr` |
| `GDEX_ABORT_TEST(msg)` | never; records `ABORT: <msg>` and stops |

Status effects: a fatal abort in a sync test ends the test with status `fail`. In an async test the abort travels through the coroutine and surfaces as status `crashed`. Either way the run exits `1`.

### Flow control

| Macro | Effect |
| --- | --- |
| `GDEX_FAIL(msg)` | Record a failure, continue. |
| `GDEX_FAIL_IF(cond, msg)` | Record a failure when `cond` holds, continue. |
| `GDEX_FAIL_UNLESS(cond, msg)` | Record a failure when `cond` does not hold, continue. |
| `GDEX_ABORT_TEST(msg)` | Record `ABORT: <msg>` and stop the body. |
| `GDEX_SKIP(msg)` | Record the test as skipped with reason `msg` and stop the body. |

### String assertions

String macros coerce both sides with `to_std_string`, so `std::string`, `const char*`, and `godot::String` mix freely in any position:

| Macro | Passes when |
| --- | --- |
| `GDEX_EXPECT_STR_EQ(a, b)` | the two strings are equal |
| `GDEX_EXPECT_STR_NE(a, b)` | the two strings differ |
| `GDEX_EXPECT_STR_CONTAINS(hay, needle)` | `hay` contains `needle` |
| `GDEX_EXPECT_STR_STARTS_WITH(hay, prefix)` | `hay` starts with `prefix` |
| `GDEX_EXPECT_STR_ENDS_WITH(hay, suffix)` | `hay` ends with `suffix` |
| `GDEX_EXPECT_STR_EMPTY(s)` | `s` is empty |
| `GDEX_EXPECT_STR_NOT_EMPTY(s)` | `s` is not empty |

```cpp
GDEX_TEST(string_utils, string_conversion_std_godot) {
    GDEX_EXPECT_STR_CONTAINS("hello world", godot::String("world"));
    GDEX_EXPECT_STR_CONTAINS(godot::String("hello world"), "hello");
    GDEX_EXPECT_STR_EQ("world", godot::String("world"));
    GDEX_EXPECT_STR_NE(godot::String("hello"), "world");
}
```

### Exception assertions

| Macro | Passes when |
| --- | --- |
| `GDEX_EXPECT_THROW(statement, ExceptionType)` | `statement` throws exactly `ExceptionType`. A different exception type also fails. |
| `GDEX_EXPECT_NO_THROW(statement)` | `statement` throws nothing. |
| `GDEX_EXPECT_ANY_THROW(statement)` | `statement` throws anything. |

### Value formatting

Comparison macros print both operands on failure. Formatting goes through `stringify(v)`:

- Default: streams the value with `operator<<`. Works for arithmetic types and `std::string`.
- `bool` prints as `true` or `false`.
- `const char*` prints quoted, or `(null)` for a null pointer.
- `godot::String` prints as UTF-8 through `to_std_string`.

A failure looks like this in the run output:

```text
    tests/counter_state_tests.cpp:12: expected bump() == 1
  expected: 1
  actual:   2
```

For other Godot types, add your own `stringify` overload next to your includes; the macros pick it up at the call site.

## Teardowns

Register cleanup callbacks with `ctx.add_teardown`:

```cpp
GDEX_TEST(files, temp_file_is_removed) {
    std::FILE *file = std::fopen("tmp_fixture.txt", "w");
    GDEX_ASSERT_NOT_NULL(file);
    ctx.add_teardown([file]() { std::fclose(file); std::remove("tmp_fixture.txt"); });
    // ... body ...
}
```

Guarantees:

- Teardowns run when the body ends, **including on aborts, throws, and skips**.
- Order is reverse registration (LIFO), so later resources free first.
- Teardowns run before the tracked-resource leak checks, so a teardown can free what `track_object` watches.
- A teardown that throws is recorded as a test failure. The remaining teardowns still run.

## Resource tracking

Two helpers catch leaks without stale-pointer dereferences:

- `ctx.track_object(ptr)` records the object's instance ID. At teardown the test fails if the ID still resolves (`leak: tracked Object instance ... is still alive`). Tracking a freed object is safe: the check resolves the ID and does not touch the pointer.
- `ctx.track_ref(ptr)` records the `RefCounted`'s initial reference count. At teardown the test fails if the count increased (`leak: tracked RefCounted reference count increased ...`).

```cpp
GDEX_TEST_T(engine, tracked_ref_is_released_cleanly, TAG_INTEGRATION) {
    godot::Ref<godot::RefCounted> value = memnew(godot::RefCounted);
    ctx.track_ref(value.ptr());
    value.unref();   // release before teardown; the test stays green
}
```

Diagnostics land in the context's failure list, so leaks fail the test like any assertion. `ctx.resource_failures()` exposes the raw messages.

## Skipping

`GDEX_SKIP(msg)` marks a test as skipped for a runtime reason and stops the body:

```cpp
GDEX_TEST(skip_demo, requires_optional_benchmark_service) {
    if (std::getenv("GDX_BENCHMARK_SERVICE") == nullptr) {
        GDEX_SKIP("precondition not met: GDX_BENCHMARK_SERVICE is unset");
    }
    // ...
}
```

- A skipped test counts in the `skip` totals, never as a pass or a failure.
- It never changes the exit code.
- The console report shows `[ SKIPPED ]` with the reason (and re-lists skips after the run); JSON reports status `skipped` with a `reason` field.
- Control never continues past the call.

Use skipping for preconditions the machine controls: missing services, timing sensitivity, platform limits.

## Patterns and pitfalls

- **Macros are statements.** Each expands to a `do { ... } while (0)` block, so they are safe inside unbraced `if`/`else` arms.
- **`ctx` must be in scope** under that exact name. The registration macro provides it; do not shadow it.
- **`suite` and `name` are identifiers**, not string literals: `GDEX_TEST(counter, starts_at_zero)`, not `GDEX_TEST("counter", ...)`.
- **One suite per topic.** The filter grammar targets `suite.name`, so a clean suite name pays off in CI.
- **Prefer expectations over fatal asserts** unless continuing is unsafe. A test that aborts early reports fewer failures.
