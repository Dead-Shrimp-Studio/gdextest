# API reference

The complete public surface of the framework. Headers live in `src/framework/`; suite
authors include `framework/assert.h` and `framework/registry.h` (paths depend on your
include setup — this repo adds `src/` to `CPPPATH`).

## Test registration

Header: `framework/registry.h`.

### `GDEX_TEST(suite, name)` / `GDEX_TEST_T(suite, name, tags)`

Declares and registers a test. `suite` and `name` must be C++ identifiers (they are
stringified for display and used in filter globs as `suite.name`). The body receives a
`TestContext&` named `ctx`, which the assertion macros reference automatically:

```cpp
GDEX_TEST(counter, bump_increments) {
    Counter c;
    c.bump();
    GDEX_EXPECT_EQ(c.value(), 1);
}

GDEX_TEST_T(slow_suite, heavy_compute, TAG_SLOW) {
    // ...
}
```

Registration happens through a static `Registrar` whose constructor calls
`TestRegistry::instance().add(...)`, so tests are registered at library load time — before
any engine interaction. `GDEX_TEST` assigns `TAG_UNIT` by default.

### `GDEX_TEST_ASYNC(suite, name)` / `GDEX_TEST_ASYNC_T(suite, name, tags)`

Declares and registers an **async test** (Milestone C): a C++20 coroutine body that may
`co_await` engine waits (see [Async tests](#async-tests)). `GDEX_TEST_ASYNC` tags the test
`TAG_ASYNC`; the `_T` variant takes explicit tags. The body receives `TestContext& ctx`
and must end with `co_return;` (a bare `return;` is not allowed inside a coroutine):

```cpp
GDEX_TEST_ASYNC(async, frames_advance) {
    const int64_t before = engine->get_process_frames();
    co_await ctx.await_frames(2);
    GDEX_EXPECT_GE(engine->get_process_frames() - before, 2);
    co_return;
}
```

### `TestCase`

```cpp
struct TestCase {
    const char *suite;    // suite name
    const char *name;     // test name
    TestFn fn;            // void (*)(TestContext&) — sync body, or null
    AsyncTestFn async_fn; // Task (*)(TestContext&) — async body, or null
    uint32_t tags;        // bitmask of Tag values
    const char *file;     // __FILE__ at registration
    int line;             // __LINE__ at registration
};
```

You normally never construct one by hand — the macros do. `TestFn` is
`void (*)(TestContext &)`; `AsyncTestFn` is `Task (*)(TestContext &)` (see
[Async tests](#async-tests)). Exactly one of `fn` / `async_fn` is set.

### `TestRegistry`

```cpp
class TestRegistry {
public:
    static TestRegistry &instance();          // function-local static — plain C++ only
    void add(TestCase tc);
    const std::vector<TestCase> &all() const;
    std::vector<const TestCase *> select(const Filter &f) const;
};
```

`select()` returns tests in run order after applying the filter, then sharding, then
shuffle (see [Filter](#filter)). `instance()` is a function-local static so no global
initialization order issues arise.

### `Filter`

```cpp
struct Filter {
    std::vector<std::string> patterns;  // positive globs + negatives ("-glob")
    uint32_t include_tags = 0;          // 0 = any tag
    uint32_t exclude_tags = 0;
    int shard_index = 0;                // 0-based
    int shard_count = 1;                // 1 = no sharding
    bool shuffle = false;
    unsigned shuffle_seed = 0;          // 0 = seed 1
    bool list_only = false;             // print selected, don't run
};
```

Selection semantics (see `registry.cpp`):

- **Glob grammar:** `*` matches any run of characters, `?` matches one, everything else is
  literal. Case-sensitive. No other regex features.
- **Pattern targets:** a pattern matches if it globs the full `suite.name`, the suite alone,
  or the name alone.
- **Positives and negatives:** if any positive (non-`-`) patterns exist, at least one must
  match; a `-`-prefixed pattern excludes any test it matches. Empty filter = all tests.
- **Tags:** `include_tags` requires the test to carry at least one of the bits;
  `exclude_tags` rejects tests carrying any of the bits.
- **Sharding:** `hash(suite) ^ (hash(name) * 2654435761) % shard_count == shard_index`
  (FNV-1a hash), so assignments are stable across runs and shards are disjoint + complete.
- **Shuffle:** Fisher–Yates with a fixed LCG seeded from `shuffle_seed` (0 → 1), so a given
  seed always produces the same order. Declaration order is preserved otherwise.

## Async tests

Header: `framework/async.h` (pure C++ core — no Godot types; the engine-boundary pump
lives in `runner.cpp`). Async tests let a body suspend across engine frames and resume
later, driven by the runner's `process_frame` pump. Suites register them with
`GDEX_TEST_ASYNC` / `GDEX_TEST_ASYNC_T` and `co_await` a wait on the test's context:

```cpp
co_await ctx.await_frames(2);      // resume after 2 process_frame ticks
co_await ctx.await_timer_ms(100);  // resume after >= 100 ms of wall clock
co_await ctx.await_frames(5, 500); // same, but fail if the wait exceeds 500 ms
```

### The coroutine type: `gdextest::Task`

`Task` is the coroutine return type behind `GDEX_TEST_ASYNC`. The runner creates the
coroutine lazily and drives it: `resume()` runs the body until it suspends (a `co_await`)
or completes. Exceptions thrown by the body — `GDEX_ABORT_TEST`, `GDEX_SKIP`, crashes — are
captured into the promise and reported the same way as for sync tests (a thrown
`TestAborted` marks the test crashed, `TestSkipped` skips it). Test authors never touch
`Task` directly.

### Waits and timeouts

- `ctx.await_frames(frames, timeout_ms = kDefaultTimeoutMs)` — resumes after `frames`
  `process_frame` ticks. `await_frames(0)` resolves immediately without consuming a tick.
- `ctx.await_timer_ms(ms, timeout_ms = 0)` — resumes after at least `ms` milliseconds
  (measured with `Time::get_ticks_msec()`). A `timeout_ms` of `0` defaults to
  `max(ms, kDefaultTimeoutMs)`, so the timer's own duration is always a valid wait.

Every suspension carries a deadline. If the wait does not resolve by its deadline, the
runner **fails the test** with a `timed out` failure (status `fail` in JSON, counted in
`fail`) and destroys the suspended coroutine — a test that never resolves is red, never a
hang. Separately, `kDefaultIsolateTimeoutSec` (60 s) bounds the **whole test**: a chain of
awaits that individually fit under the per-wait timeout but together exceed the budget is
failed too.

### Semantics

- Async tests run **one at a time, in declaration order** — the pump never interleaves
  two bodies, so results stay deterministic.
- Async tests require the live engine (the pump advances on real frames). If a body
  `co_await`s with no pump active — e.g. `co_await` inside a plain `GDEX_TEST` — the await
  records a failure ("used outside an async test run") and the body continues.
- Self-tests verify the machinery headlessly through `SubAsyncPump`, which simulates
  `process_frame` ticks and a monotonic ms clock (see [Runner entry points](#runner-entry-points)).

## Assertions

Header: `framework/assert.h`. Every macro records a failure on the in-scope `ctx` and
**continues execution** — only `GDEX_ABORT_TEST` aborts the test.

| Macro | Passes when | Failure message includes |
| --- | --- | --- |
| `GDEX_EXPECT(cond)` | `cond` is truthy | the expression text |
| `GDEX_EXPECT_TRUE(cond)` | alias of `GDEX_EXPECT` | — |
| `GDEX_EXPECT_FALSE(cond)` | `cond` is falsy | the expression text |
| `GDEX_EXPECT_EQ(a, b)` | `a == b` | `expected a == b` + formatted `a`, `b` |
| `GDEX_EXPECT_NE(a, b)` | `a != b` | lhs/rhs formatted |
| `GDEX_EXPECT_LT/LE/GT/GE(a, b)` | `a < b`, `a <= b`, `a > b`, `a >= b` | lhs/rhs formatted |
| `GDEX_EXPECT_NEAR(a, b, eps)` | `|a − b| <= eps` (as `double`) | lhs/rhs formatted |
| `GDEX_EXPECT_STR_EQ(a, b)` | `std::string(a) == std::string(b)` | both strings |
| `GDEX_EXPECT_STR_CONTAINS(hay, needle)` | `hay` contains `needle` | both strings |
| `GDEX_EXPECT_NULL(p)` | `p == nullptr` | the expression text |
| `GDEX_EXPECT_NOT_NULL(p)` | `p != nullptr` | the expression text |
| `GDEX_FAIL(msg)` | never | `msg` |
| `GDEX_ABORT_TEST(msg)` | never — records `"ABORT: " + msg` then throws | the message |
| `GDEX_SKIP(msg)` | — (skips, never a pass or failure) | the reason `msg` |

`GDEX_ABORT_TEST` throws a private `TestAborted` type caught inside the runner's frame; it
marks the test as crashed. It never propagates out of the framework.

`GDEX_SKIP(msg)` throws a private `TestSkipped` type (also caught inside the runner's
frame). It records the test as **skipped** with reason `msg` and stops the body — control
never continues past the call. A skipped test counts in the `skip` totals, not in
`pass`/`fail`, and does not change the exit code. It is meant for runtime preconditions
(missing fixture/service, timing, platform), e.g.:

```cpp
GDEX_TEST(feature, needs_optional_service) {
    if (!service_available()) GDEX_SKIP("optional service not present");
    // ... test logic ...
}
```

### Value formatting (`stringify<T>`)

Comparison macros format operands with `gdextest::stringify(v)`:

- Default: streams the value (`std::ostringstream << v`) — works for arithmetic types,
  `std::string`, enums with `operator<<`, etc.
- `bool` → `"true"` / `"false"`.
- `const char*` → quoted, or `(null)`.

To format Godot types (`String`, `Variant`, …), add `stringify` overloads — engine types
are only touched at this value-formatting boundary, keeping the core `std::string`-based.

## TestContext

Header: `framework/context.h`.

```cpp
struct Failure {
    std::string file;
    int line = 0;
    std::string message;
};

class TestContext {
public:
    void fail(const char *file, int line, std::string message);  // record, never throw
    bool ok() const;
    int failure_count() const;
    const std::vector<Failure> &failures() const;
    [[noreturn]] static void abort_test(const char *file, int line, std::string message);
    [[noreturn]] static void skip(const char *file, int line, std::string reason);

    bool skipped() const;                       // true after GDEX_SKIP
    const std::string &skip_reason() const;     // the reason passed to GDEX_SKIP

    void set_engine(void *engine);       // set by the runner in engine-triggered runs
    void *engine_handle() const;         // opaque live-engine host, or null

    // Async waits (Milestone C): awaitables for `co_await` in GDEX_TEST_ASYNC bodies
    // (defined in async.h). See [Async tests](#async-tests).
    FrameAwaiter await_frames(int64_t frames, int64_t timeout_ms = kDefaultTimeoutMs);
    TimerAwaiter await_timer_ms(int64_t ms, int64_t timeout_ms = 0);

    void track_object(void *obj);  // M4 stub — leak/UAF tracking hooks
    void track_ref(void *ref);     // M4 stub
};
```

The runner constructs one `TestContext` per test and injects it as `ctx`. `abort_test` is
the implementation behind `GDEX_ABORT_TEST`; it records on the currently-active context
before throwing. `await_frames`/`await_timer_ms` return the awaitables used with `co_await`
in async test bodies; their implementations live in `async.h` (the forward declarations in
`context.h` keep the coroutine machinery out of the core header).
`track_object`/`track_ref` are declared so assertion code can reference them without
`#ifdef` churn; the tracking implementation is a later milestone.

The engine handle is an opaque `void*` so the core stays Godot-free. When a run happens
through the engine trigger, the runner sets it to the live host node; engine-boundary
accessors in [`framework/engine.h`](../src/framework/engine.h) cast it to a real
`godot::Node`/`godot::SceneTree` (see [Live-engine tests](#live-engine-tests)).

## Live-engine tests

Header: `framework/engine.h` (engine boundary — the second framework header that pulls in
godot-cpp, alongside `runner.h`).

```cpp
namespace gdextest {
// The host Node the adapter ran from, or null when no engine is attached.
godot::Node *engine_node(TestContext &ctx);
// The live SceneTree (engine_node(ctx)->get_tree()), or null.
godot::SceneTree *engine_tree(TestContext &ctx);
}  // namespace gdextest
```

Include this header and tag the test `GDEX_TEST_T(..., TAG_INTEGRATION)` to reach the live
engine: singletons, `ClassDB`, and building real scene-tree structure (`memnew`,
`add_child`, `remove_child`, `memdelete`). These functions return null for pure
(non-engine-triggered) invocations, so guard the result before dereferencing.

## Host configuration

Header: `framework/host.h`.

The default adapter uses explicit function pointers instead of weak symbols, so consumer
startup and shutdown hooks work consistently across GCC, Clang, and MSVC:

```cpp
namespace gdextest {
struct HostConfig {
    void (*bootstrap)() = nullptr;
    void (*shutdown)() = nullptr;
};
void configure_host(const HostConfig &config);
}
```

Call `configure_host()` from the consumer extension's initialized startup path. The
callbacks run on the Godot main thread: `bootstrap` immediately before the test run and
`shutdown` after reporting. An empty `HostConfig` restores the no-op default.

## Runner entry points

Header: `framework/runner.h`. Only the engine-boundary headers (`runner.h`, `engine.h`)
pull in godot-cpp.

```cpp
namespace gdextest {

// Called by the host adapter with any Node whose get_tree() yields the live SceneTree.
// No-op unless triggered (GDX_RUN_TESTS env, or --gdextest-run in either cmdline list).
// Exit codes: 0 = all passed, 1 = ≥1 failure, 2 = usage error (malformed/unknown option).
void run_all_and_quit(void *tree_node);

// Run a single test body with a fresh TestContext; return its failure count.
// Used by the self-test suite to verify assertion macros.
int run_sub_and_count_failures(void (*body)(TestContext &));

// Run a single test body with a fresh TestContext and write its result as a
// single-entry JSON document to `path` (same schema as --gdextest-json).
// Returns the body's failure count.
int run_sub_and_write_json(void (*body)(TestContext &), const char *path);

// Manual frame pump for async self-tests (no engine): simulates process_frame
// ticks and a monotonic ms clock so the coroutine machinery (suspend/resume,
// per-wait timeout, isolate budget) is verifiable headlessly.
class SubAsyncPump {
public:
    // Start an async body on a fresh simulated clock; true if it suspended.
    bool start(std::function<Task(TestContext &)> body, TestContext &ctx);
    // Advance one simulated frame (+tick_ms); false once the body finished/failed.
    bool step(int64_t tick_ms = 16);
};

// Drive an async body to completion through SubAsyncPump and write its result
// as a single-entry JSON document to `path` (same schema as --gdextest-json).
// Returns the body's failure count.
int run_sub_async_write_json(std::function<Task(TestContext &)> body, const char *path);

}  // namespace gdextest
```

`run_all_and_quit` needs a live `SceneTree` to call `quit()` — the adapter must only invoke
it from a verified hook point (the editor plugin's `_ready()` in this repo's reference
setup). The runner tolerates a null tree for the run itself, but `quit()` needs it. With
async tests selected, `run_all_and_quit` may return before the run completes: the
`process_frame` pump it connects resumes suspended coroutines on later frames and calls
`quit()` itself once every test has finished.

## Configuration

Header: `framework/config.h` — the single customization point for hosts.

```cpp
enum Tag : uint32_t {
    TAG_UNIT        = 1 << 0,
    TAG_INTEGRATION = 1 << 1,
    TAG_ASYNC       = 1 << 2,
    TAG_SLOW        = 1 << 3,
    TAG_FLAKY       = 1 << 4,
};

inline constexpr int kDefaultTimeoutMs = 30000;        // per-wait timeout for co_await waits
inline constexpr int kDefaultFlakyRetries = 3;         // flaky retry budget
inline constexpr int kDefaultIsolateTimeoutSec = 60;   // per-test budget for a whole async test
```

Hosts with a naming clash (or different budgets) redefine these in this header only — per
the plan's §15 boundary convention.
