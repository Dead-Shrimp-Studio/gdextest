# API reference

The complete public surface of the framework. Headers live in `src/framework/`; suite
authors include `framework/assert.h` and `framework/registry.h` (paths depend on your
include setup — this repo adds `src/` to `CPPPATH`).

## Test registration

Header: `framework/registry.h`.

### `GDX_TEST(suite, name)` / `GDX_TEST_T(suite, name, tags)`

Declares and registers a test. `suite` and `name` must be C++ identifiers (they are
stringified for display and used in filter globs as `suite.name`). The body receives a
`TestContext&` named `ctx`, which the assertion macros reference automatically:

```cpp
GDX_TEST(counter, bump_increments) {
    Counter c;
    c.bump();
    GDX_EXPECT_EQ(c.value(), 1);
}

GDX_TEST_T(slow_suite, heavy_compute, TAG_SLOW) {
    // ...
}
```

Registration happens through a static `Registrar` whose constructor calls
`TestRegistry::instance().add(...)`, so tests are registered at library load time — before
any engine interaction. `GDX_TEST` assigns `TAG_UNIT` by default.

### `TestCase`

```cpp
struct TestCase {
    const char *suite;   // suite name
    const char *name;    // test name
    TestFn fn;           // void (*)(TestContext&)
    uint32_t tags;       // bitmask of Tag values
    const char *file;    // __FILE__ at registration
    int line;            // __LINE__ at registration
};
```

You normally never construct one by hand — the macros do. `TestFn` is
`void (*)(TestContext &)`.

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

## Assertions

Header: `framework/assert.h`. Every macro records a failure on the in-scope `ctx` and
**continues execution** — only `GDX_ABORT_TEST` aborts the test.

| Macro | Passes when | Failure message includes |
| --- | --- | --- |
| `GDX_EXPECT(cond)` | `cond` is truthy | the expression text |
| `GDX_EXPECT_TRUE(cond)` | alias of `GDX_EXPECT` | — |
| `GDX_EXPECT_FALSE(cond)` | `cond` is falsy | the expression text |
| `GDX_EXPECT_EQ(a, b)` | `a == b` | `expected a == b` + formatted `a`, `b` |
| `GDX_EXPECT_NE(a, b)` | `a != b` | lhs/rhs formatted |
| `GDX_EXPECT_LT/LE/GT/GE(a, b)` | `a < b`, `a <= b`, `a > b`, `a >= b` | lhs/rhs formatted |
| `GDX_EXPECT_NEAR(a, b, eps)` | `|a − b| <= eps` (as `double`) | lhs/rhs formatted |
| `GDX_EXPECT_STR_EQ(a, b)` | `std::string(a) == std::string(b)` | both strings |
| `GDX_EXPECT_STR_CONTAINS(hay, needle)` | `hay` contains `needle` | both strings |
| `GDX_EXPECT_NULL(p)` | `p == nullptr` | the expression text |
| `GDX_EXPECT_NOT_NULL(p)` | `p != nullptr` | the expression text |
| `GDX_FAIL(msg)` | never | `msg` |
| `GDX_ABORT_TEST(msg)` | never — records `"ABORT: " + msg` then throws | the message |

`GDX_ABORT_TEST` throws a private `TestAborted` type caught inside the runner's frame; it
marks the test as crashed. It never propagates out of the framework.

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

    void track_object(void *obj);  // M4 stub — leak/UAF tracking hooks
    void track_ref(void *ref);     // M4 stub
};
```

The runner constructs one `TestContext` per test and injects it as `ctx`. `abort_test` is
the implementation behind `GDX_ABORT_TEST`; it records on the currently-active context
before throwing. `track_object`/`track_ref` are declared so assertion code can reference
them without `#ifdef` churn; the tracking implementation is a later milestone.

## Runner entry points

Header: `framework/runner.h`. This is the **only** framework header that pulls in
godot-cpp.

```cpp
namespace gdextest {

// Called by the host adapter with any Node whose get_tree() yields the live SceneTree.
// No-op unless triggered (GDX_RUN_TESTS env, or --gdxtest-run in either cmdline list).
// Exit codes: 0 = all passed, 1 = ≥1 failure, 2 = usage error (reserved).
void run_all_and_quit(void *tree_node);

// Run a single test body with a fresh TestContext; return its failure count.
// Used by the self-test suite to verify assertion macros.
int run_sub_and_count_failures(void (*body)(TestContext &));

}  // namespace gdextest
```

`run_all_and_quit` needs a live `SceneTree` to call `quit()` — the adapter must only invoke
it from a verified hook point (the editor plugin's `_ready()` in this repo's reference
setup). The runner tolerates a null tree for the run itself, but `quit()` needs it.

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

inline constexpr int kDefaultTimeoutMs = 30000;        // per async wait (M2)
inline constexpr int kDefaultFlakyRetries = 3;         // flaky retry budget
inline constexpr int kDefaultIsolateTimeoutSec = 60;   // isolate time budget
```

Hosts with a naming clash (or different budgets) redefine these in this header only — per
the plan's §15 boundary convention.
