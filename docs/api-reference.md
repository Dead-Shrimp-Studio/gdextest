---
title: "API reference"
description: "The complete public API, header by header."
order: 90
sidebar: "Reference"
draft: false
---

# API reference

The complete public surface of the framework, header by header. Headers live in `include/gdextest/`. Suite authors include `gdextest/assert.h` and `gdextest/registry.h`; the SConscript adds `include/` to the test target's include path, so the includes resolve as `gdextest/...`.

## Headers

| Header | Contents | Pulls in godot-cpp |
| --- | --- | --- |
| `gdextest/registry.h` | `GDEX_TEST*` macros, `TestCase`, `TestFn`, `AsyncTestFn`, `TestRegistry`, `Filter`, `Registrar` | no |
| `gdextest/assert.h` | All assertion and flow-control macros, `stringify`, `to_std_string` (std overloads) | transitively, via `strings.h` / `signals.h` |
| `gdextest/context.h` | `TestContext`, `Failure`, `Teardown` | no (opaque engine handle) |
| `gdextest/async.h` | `Task`, `FrameAwaiter`, `TimerAwaiter`, `AsyncCoordinator`, `AwaitRequest` | no |
| `gdextest/config.h` | `Tag` enum, budget defaults, `RuntimeConfig`, `runtime_config()` | no |
| `gdextest/engine.h` | `engine_node`, `engine_tree` | yes |
| `gdextest/strings.h` | `to_std_string` godot::String overload | yes |
| `gdextest/signals.h` | `SignalMonitor`, `SignalData` | yes |
| `gdextest/host.h` | `HostConfig`, `configure_host`, `bootstrap_host`, `shutdown_host` | no |
| `gdextest/adapter.h` | `ExtensionAdapter`, `AdapterRegistry`, `AdapterRegistrar`, `GDEX_REGISTER_ADAPTER` | yes |
| `gdextest/runner.h` | `run_all_and_quit`, `run_sub_*`, `SubAsyncPump` | no (opaque node handle) |

Engine-boundary implementation files: `src/framework/runner.cpp` and `src/framework/signals.cpp`, plus `src/gdextest_entry.cpp` and the adapter source.

## Test registration

Header: `gdextest/registry.h`.

### Macros

| Macro | Registers |
| --- | --- |
| `GDEX_TEST(suite, name)` | Sync body, tag `TAG_UNIT`. |
| `GDEX_TEST_T(suite, name, tags)` | Sync body, your tags. |
| `GDEX_TEST_ASYNC(suite, name)` | Coroutine body, tag `TAG_ASYNC`. |
| `GDEX_TEST_ASYNC_T(suite, name, tags)` | Coroutine body, your tags. |

- `suite` and `name` must be C++ identifiers; they are stringified for display and filters.
- Each macro declares a static function, registers it through a static `Registrar`, and opens the body.
- The body receives `::gdextest::TestContext &ctx`.
- Sync bodies are `void`; async bodies return `gdextest::Task` and must use `co_return`.
- Bare tag names (`TAG_UNIT`, `TAG_INTEGRATION`, ...) resolve inside the macros from any namespace.

```cpp
GDEX_TEST(counter, bump_increments) {
    Counter c;
    c.bump();
    GDEX_EXPECT_EQ(c.value(), 1);
}
```

### Types

```cpp
using TestFn = void (*)(TestContext &);
using AsyncTestFn = Task (*)(TestContext &);

struct TestCase {
    const char *suite;
    const char *name;
    TestFn fn;             // sync body, or null
    AsyncTestFn async_fn;  // coroutine body, or null
    uint32_t tags;         // bitmask of Tag values
    const char *file;      // __FILE__ at registration
    int line;              // __LINE__ at registration
};

class TestRegistry {
public:
    static TestRegistry &instance();               // function-local static
    void add(TestCase tc);
    const std::vector<TestCase> &all() const;
    std::vector<const TestCase *> select(const Filter &f) const;
};

struct Registrar {
    explicit Registrar(const TestCase &tc);        // calls TestRegistry::add
};
```

`select()` returns the selected tests in run order: filter first, then shard, then shuffle. Declaration order is preserved otherwise.

### `Filter`

```cpp
struct Filter {
    std::vector<std::string> patterns;  // positive globs + negatives ("-glob")
    uint32_t include_tags = 0;          // 0 = any tag
    uint32_t exclude_tags = 0;          // reject tests carrying any of these bits
    int shard_index = 0;                // 0-based
    int shard_count = 1;                // 1 = no sharding
    bool shuffle = false;
    unsigned shuffle_seed = 0;          // 0 means seed 1
    bool list_only = false;             // print selected, do not run
};
```

Selection semantics:

- **Glob grammar:** `*` matches any run of characters, `?` matches one, everything else is literal. Case-sensitive. No regex.
- **Pattern targets:** a pattern matches the full `suite.name`, the suite alone, or the name alone.
- **Positives and negatives:** with any positive patterns present, at least one must match. A `-`-prefixed pattern excludes any test it matches. An empty filter selects all tests.
- **Tags:** `include_tags` requires at least one of the bits; `exclude_tags` rejects any carrier. The CLI sets no tag flags; use the `Filter` API directly (as the framework's own tests do).
- **Sharding:** `hash(suite) ^ (hash(name) * 2654435761) % shard_count == shard_index`, with FNV-1a hashes. Assignments are stable; shards are disjoint and complete.
- **Shuffle:** Fisher-Yates driven by a fixed LCG (`s = s * 1103515245 + 12345`), seeded from `shuffle_seed` (0 becomes 1). A given seed always produces the same order.

## Assertions

Header: `gdextest/assert.h`. All macros are statements that record on the in-scope `ctx`. See [Writing tests](/projects/gdextest/docs/writing-tests) for usage guidance and failure-message examples.

### Non-fatal expectations

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
| `GDEX_EXPECT_NEAR(a, b, eps)` | absolute `a - b` at most `eps`, compared as `double` |
| `GDEX_EXPECT_NULL(p)` | `p == nullptr` |
| `GDEX_EXPECT_NOT_NULL(p)` | `p != nullptr` |

### Fatal assertions

Each records the failure and then aborts the test. The abort throws the private `TestAborted` type, caught inside the runner's frame.

| Macro | Passes when |
| --- | --- |
| `GDEX_ASSERT_TRUE(cond)` | `cond` is truthy |
| `GDEX_ASSERT_FALSE(cond)` | `cond` is falsy |
| `GDEX_ASSERT_EQ(a, b)` | `a == b` |
| `GDEX_ASSERT_NE(a, b)` | `a != b` |
| `GDEX_ASSERT_NULL(p)` | `p == nullptr` |
| `GDEX_ASSERT_NOT_NULL(p)` | `p != nullptr` |

Status effects: a fatal abort in a sync test ends with status `fail` (the recorded message starts with `ABORT:`). In an async test the abort surfaces as status `crashed`.

### Flow control

| Macro | Effect |
| --- | --- |
| `GDEX_FAIL(msg)` | Record `msg`, continue. |
| `GDEX_FAIL_IF(cond, msg)` | Record when `cond` holds, continue. |
| `GDEX_FAIL_UNLESS(cond, msg)` | Record when `cond` does not hold, continue. |
| `GDEX_ABORT_TEST(msg)` | Record `ABORT: <msg>`, stop the test. |
| `GDEX_SKIP(msg)` | Record the test as skipped with reason `msg`, stop the test. Throws the private `TestSkipped` type. |

A skipped test counts in the `skip` totals, never as pass or fail, and never changes the exit code.

### String assertions

Both sides are coerced with the `to_std_string` overloads, so `std::string`, `const char*`, and `godot::String` mix in any position. The godot overload comes from `strings.h`, which `assert.h` includes.

| Macro | Passes when |
| --- | --- |
| `GDEX_EXPECT_STR_EQ(a, b)` | the strings are equal |
| `GDEX_EXPECT_STR_NE(a, b)` | the strings differ |
| `GDEX_EXPECT_STR_CONTAINS(hay, needle)` | `hay` contains `needle` |
| `GDEX_EXPECT_STR_STARTS_WITH(hay, prefix)` | `hay` starts with `prefix` |
| `GDEX_EXPECT_STR_ENDS_WITH(hay, suffix)` | `hay` ends with `suffix` |
| `GDEX_EXPECT_STR_EMPTY(s)` | `s` is empty |
| `GDEX_EXPECT_STR_NOT_EMPTY(s)` | `s` is not empty |

### Exception assertions

| Macro | Passes when |
| --- | --- |
| `GDEX_EXPECT_THROW(statement, ExceptionType)` | `statement` throws exactly `ExceptionType`; any other type also fails |
| `GDEX_EXPECT_NO_THROW(statement)` | `statement` throws nothing; `std::exception::what` is included in the failure |
| `GDEX_EXPECT_ANY_THROW(statement)` | `statement` throws anything |

### Value formatting

Comparison macros render operands with `gdextest::stringify(v)`:

- Default: `std::ostringstream << v`. Works for arithmetic types, `std::string`, and anything with `operator<<`.
- `bool` prints as `true` or `false`.
- `const char*` prints quoted, or `(null)` for a null pointer.
- `godot::String` prints as UTF-8 through `to_std_string`.

Add `stringify` overloads for other Godot types at the call site; the macros resolve them there.

## TestContext

Header: `gdextest/context.h`.

```cpp
struct Failure {
    std::string file;
    int line = 0;
    std::string message;
};

using Teardown = std::function<void()>;

class TestContext {
public:
    void fail(const char *file, int line, std::string message);  // record, never throw
    bool ok() const;
    int failure_count() const;
    const std::vector<Failure> &failures() const;

    [[noreturn]] static void abort_test(const char *file, int line, std::string message);
    [[noreturn]] static void skip(const char *file, int line, std::string reason);

    bool skipped() const;
    const std::string &skip_reason() const;

    void add_teardown(Teardown teardown);
    const std::vector<Teardown> &teardowns() const;

    void track_object(void *obj);   // a live godot::Object*
    void track_ref(void *ref);      // a live godot::RefCounted*
    const std::vector<std::string> &resource_failures() const;

    void set_engine(void *engine);  // the runner sets this in engine runs
    void *engine_handle() const;

    SignalMonitor &signals();       // lazily created; freed by a registered teardown

    FrameAwaiter await_frames(int64_t frames, int64_t timeout_ms = 0);
    TimerAwaiter await_timer_ms(int64_t ms, int64_t timeout_ms = 0);
};
```

Behavior notes:

- The runner constructs one context per test (per attempt, for retried tests) and injects it as `ctx`.
- `abort_test` records on the currently active context before throwing. It backs `GDEX_ABORT_TEST` and the `GDEX_ASSERT_*` macros.
- `skip` marks the context skipped and throws `TestSkipped`. It backs `GDEX_SKIP`.
- Teardowns run LIFO when the body ends, including on aborts, throws, and skips. They run before the tracked-resource checks. A throwing teardown is recorded as a failure; the remaining teardowns still run.
- `track_object` records the instance ID and fails the test at teardown when the ID still resolves. `track_ref` records the initial reference count and fails when the count increased.
- `engine_handle()` is an opaque pointer; `engine.h` casts it to `godot::Node*` / `godot::SceneTree*`. Null outside engine-triggered runs.
- `signals()` is implemented in `signals.cpp` (engine boundary). The first call creates the monitor; a teardown disconnects and frees it.

## Async tests

Header: `gdextest/async.h`. Pure C++; no Godot types. The engine-boundary pump lives in `runner.cpp`.

### `Task`

The coroutine return type behind `GDEX_TEST_ASYNC`. Lazily started: the body runs on the first `resume()` and suspends at each `co_await`. The final suspend stays suspended, so the owner must destroy the `Task` to free the frame; the runner does. Exceptions from the body are captured into the promise and surfaced through `exception()` after completion. Test authors never touch `Task` directly.

```cpp
class Task {
public:
    struct promise_type;              // get_return_object, initial/final suspend, unhandled_exception
    bool done() const;
    void resume();
    std::exception_ptr exception() const;
    // Move-only; the destructor destroys the coroutine frame.
};
```

### Waits

| Call | Meaning |
| --- | --- |
| `ctx.await_frames(frames, timeout_ms = 0)` | Resume after `frames` `process_frame` ticks. `frames == 0` resolves immediately. |
| `ctx.await_timer_ms(ms, timeout_ms = 0)` | Resume after at least `ms` milliseconds on the engine clock. |

- `timeout_ms == 0` uses `runtime_config().timeout_ms` (from `--gdextest-timeout-ms`).
- `await_timer_ms` with `timeout_ms == 0` uses the larger of `ms` and the configured default, so the wait itself is always within its own budget.
- Each suspension gets a deadline when the driver first observes it. A resolution wins over a coincident deadline.
- An await with no active driver records a failure (`used outside an async test run`) and does not suspend.

### `AwaitRequest` and `AsyncCoordinator`

```cpp
enum class AwaitKind { Frames, TimerMs };
enum class AwaitStatus { Pending, Resolved, TimedOut };

struct AwaitRequest {
    AwaitKind kind;
    int64_t frames_left;     // Frames
    int64_t duration_ms;     // TimerMs
    int64_t timeout_ms;      // deadline budget for this wait
    std::string description; // used in timeout messages
    int64_t resume_at_ms;    // TimerMs absolute resume time, stamped by the driver
    int64_t deadline_ms;     // absolute failure time, stamped by the driver
};

class AsyncCoordinator {  // singleton; one active suspension at a time
public:
    static AsyncCoordinator &instance();
    void suspend(std::coroutine_handle<> handle, AwaitRequest request);
    bool has_pending() const;
    std::coroutine_handle<> current() const;
    const AwaitRequest &request() const;
    void stamp(int64_t now_ms);              // convert relative request to absolute times
    AwaitStatus advance(int64_t now_ms);     // one pump tick
    bool driver_active() const;
    void set_driver_active(bool active);
    void clear();
};
```

The runner and `SubAsyncPump` are the only drivers. `advance()` decrements frame counts or checks elapsed time, then checks the deadline; `Pending` means keep waiting.

## SignalMonitor

Header: `gdextest/signals.h` (engine boundary); implementation in `src/framework/signals.cpp`. Registered as a Godot class at the editor initialization level. Get the per-test instance with `ctx.signals()`; the framework disconnects and frees it through a teardown.

```cpp
class SignalMonitor : public Object {
public:
    // Watching (supports fluent chaining)
    void add(Object *target, const String &signal_name, int expected = 0);
    void add_all(Object *target, const std::vector<String> &signals, int expected = 0);
    void remove(Object *target, const String &signal_name);
    void remove_all();

    // State resetting
    void reset(Object *target, const String &signal_name);
    void reset_all();

    // Queries
    bool was_emitted(Object *target, const String &signal_name) const;
    int get_emission_count(Object *target, const String &signal_name) const;
    std::vector<Variant> get_last_arguments(Object *target, const String &signal_name) const;
    Variant get_argument(Object *target, const String &signal_name,
                         size_t emission_index, size_t arg_index) const;
    const std::vector<std::vector<Variant>> &get_emission_history(Object *target,
                                                                  const String &signal_name) const;

    // Verdict: true when every watched signal's count equals its expectation
    bool evaluate() const;
};
```

- `add` connects a bound vararg receiver, so emissions of any arity are recorded with their full argument list.
- `expected` defaults to `0`: the signal must not fire.
- `get_emission_history` returns an empty vector for unknown or reset entries.
- Queries on a null target return zero values; they never crash.

## String coercion

Header: `gdextest/strings.h` (engine boundary). Included by `assert.h`.

```cpp
namespace gdextest {
std::string to_std_string(const godot::String &value);  // UTF-8
std::string to_std_string(const std::string &value);    // identity
std::string to_std_string(const char *value);           // null -> "(null)"
}
```

The `GDEX_EXPECT_STR_*` macros and the `stringify` godot overload call `to_std_string` at the macro-expansion site, so mixed-type string assertions just work.

## Engine accessors

Header: `gdextest/engine.h` (engine boundary).

```cpp
namespace gdextest {
godot::Node *engine_node(TestContext &ctx);      // host node, or null
godot::SceneTree *engine_tree(TestContext &ctx); // engine_node(ctx)->get_tree(), or null
}
```

Both return null when no engine is attached. Guard before dereferencing.

## Host configuration

Header: `gdextest/host.h`.

```cpp
namespace gdextest {
struct HostConfig {
    void (*bootstrap)() = nullptr;
    void (*shutdown)() = nullptr;
};

void configure_host(const HostConfig &config);
void bootstrap_host();   // runs config.bootstrap, or nothing
void shutdown_host();    // runs config.shutdown, or nothing
}
```

The reference adapter calls `bootstrap_host()` right before a triggered run; the runner calls `shutdown_host()` after reporting. An empty config restores the no-op default.

## Adapters

Header: `gdextest/adapter.h` (engine boundary: it names `godot::Node`).

```cpp
class ExtensionAdapter {
public:
    virtual ~ExtensionAdapter() = default;
    virtual void on_initialize(godot::ModuleInitializationLevel level) {}
    virtual void on_uninitialize(godot::ModuleInitializationLevel level) {}
    virtual void on_ready(godot::Node *tree_node) {}
};

class AdapterRegistry {  // singleton
public:
    static AdapterRegistry &instance();
    void add_adapter(ExtensionAdapter *adapter);
    const std::vector<ExtensionAdapter *> &adapters() const;
    void dispatch_initialize(godot::ModuleInitializationLevel level);   // registration order
    void dispatch_uninitialize(godot::ModuleInitializationLevel level); // reverse order (LIFO)
    void dispatch_ready(godot::Node *tree_node);                        // registration order
};

template <typename T>
struct AdapterRegistrar {  // constructs a static T and registers it
    AdapterRegistrar();
};
```

Macro:

```cpp
#define GDEX_REGISTER_ADAPTER(AdapterClass)  // file-static AdapterRegistrar<AdapterClass>
```

Contract function, implemented by the adapter source (`src/support/adapter.cpp` by default):

```cpp
namespace gdextest_adapter {
void maybe_run(godot::Node *tree_node);  // trigger check -> dispatch_ready -> bootstrap -> run
}
```

The entry point dispatches `initialize` / `uninitialize` at each module level; the adapter dispatches `ready` before a triggered run.

## Runner entry points

Header: `gdextest/runner.h`. Used by the adapter, the framework's self-tests, and custom hosts.

```cpp
namespace gdextest {

// Called by the adapter with any Node whose get_tree() yields the live SceneTree.
// No-op unless triggered (GDX_RUN_TESTS env, or --gdextest-run in either argument
// list). Exit codes: 0 all passed, 1 any failure, 2 usage error.
void run_all_and_quit(void *tree_node);

// Run one sync body with a fresh TestContext; return its failure count.
int run_sub_and_count_failures(void (*body)(TestContext &));

// Run one sync body and write its result as a single-entry JSON document
// (same schema as --gdextest-json). Returns the failure count.
int run_sub_and_write_json(void (*body)(TestContext &), const char *path);

// Manual frame pump for headless self-tests: simulates process_frame ticks and a
// monotonic millisecond clock so the coroutine machinery is verifiable without
// an engine.
class SubAsyncPump {
public:
    // Start an async body on a fresh simulated clock (t = 0). True when the body
    // suspended (call step()); false when it completed at once.
    bool start(std::function<Task(TestContext &)> body, TestContext &ctx);

    // Advance one simulated frame and tick_ms of simulated time. True while the
    // body is still pending; false once it completed or was failed.
    bool step(int64_t tick_ms = 16);
};

// Drive an async body to completion through SubAsyncPump and write its result as
// a single-entry JSON document. Returns the failure count.
int run_sub_async_write_json(std::function<Task(TestContext &)> body, const char *path);

}  // namespace gdextest
```

`run_all_and_quit` needs a live `SceneTree` to call `quit()`. With async tests selected it may return before the run completes; the `process_frame` pump it connects resumes suspended coroutines on later frames and calls `quit()` itself once every test has finished.

## Configuration constants

Header: `gdextest/config.h` — the single customization point for hosts.

```cpp
enum Tag : uint32_t {
    TAG_UNIT        = 1 << 0,
    TAG_INTEGRATION = 1 << 1,
    TAG_ASYNC       = 1 << 2,
    TAG_SLOW        = 1 << 3,
    TAG_FLAKY       = 1 << 4,
};

inline constexpr int kDefaultTimeoutMs        = 30000;  // per async wait
inline constexpr int kDefaultFlakyRetries     = 3;      // TAG_FLAKY retry budget
inline constexpr int kDefaultIsolateTimeoutSec = 60;    // whole-test async budget

struct RuntimeConfig {
    int timeout_ms;
    int isolate_timeout_sec;
    int flaky_retries;
};

inline RuntimeConfig &runtime_config();  // single per-program instance
```

The runner overrides these from the `--gdextest-*` budget flags, which the CLI fills from `[gdextest.test]`. Hosts with a naming clash redefine the constants in this header only.
