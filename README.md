# gdextest — GDExtension testing framework

A C++ testing framework for [Godot](https://godotengine.org) GDExtensions. Suites are plain
C++ compiled into a test library and run **inside a headless Godot binary** — no separate
runner process, no scripting layer. One command builds, generates a fixture project,
launches Godot, and returns `0`/`1` from the run.

Write googletest-style tests for pure logic or the live engine — singletons, scene trees,
your own registered classes, `Variant`/`String` round-trips — with async (multi-frame)
tests, flaky retries, per-test teardown tracking, editor and runtime host modes, and
CI-friendly JSON/JUnit output with filtering, sharding, and shard merging.

## Quickstart

Add the framework as a submodule, write a suite, run one command:

```bash
git submodule add <this repo> extern/gdextest
git submodule update --init
```

```cpp
// tests/smoke.cpp
#include "gdextest/assert.h"
#include "gdextest/registry.h"

GDEX_TEST(smoke, framework_is_wired) {
    GDEX_EXPECT(true);
}
```

```bash
./extern/gdextest/gdextest test
```

That is the whole integration. `test` writes `.gdextest.toml` if it is missing (never
overwrites one that exists), runs the doctor preflight (config, Godot, SCons, godot-cpp
version, test sources), builds the test library and fixture, warms the fixture cache,
launches Godot headlessly, and exits `0` on a green run, `1` on failures.

**No `SConstruct` wiring required.** If your build file doesn't call the framework
SConscript, `test` builds through a temporary injected copy (`SConstruct.gdextest`,
removed afterwards) — your build file is never touched. `./extern/gdextest/gdextest
scaffold --apply` is only for making that wiring permanent or for a custom entry point /
plugin class (it backs up `SConstruct` first and generates `testsupport/entry.cpp` from
your TOML values).

Prerequisites: `scons`, a C++20 toolchain, and a Godot 4.5 binary. Godot is auto-discovered
(project, ancestor directories, `$HOME`, `PATH`), and the doctor flags a godot-cpp version
mismatch before the compile step. The framework reuses your existing `extern/godot-cpp` —
the submodule's nested copy is only used by the framework's own self-tests.

## Writing tests

Suites are C++ files using the `GDEX_TEST` macro and `GDEX_EXPECT_*` assertions. A test
body receives a `TestContext&` named `ctx` (injected by the runner), so macros reference it
automatically:

```cpp
GDEX_TEST(counter, bump_increments) {
    Counter c;
    c.bump();
    GDEX_EXPECT_EQ(c.value(), 1);
}
```

Assertions record failures and keep going (they never throw), so one test reports every
failing check:

| Macro | Checks |
| --- | --- |
| `GDEX_EXPECT(cond)`, `GDEX_EXPECT_TRUE/FALSE` | boolean conditions |
| `GDEX_EXPECT_EQ/NE/LT/LE/GT/GE(a, b)` | comparisons with value formatting |
| `GDEX_EXPECT_NEAR(a, b, eps)` | floating-point tolerance |
| `GDEX_EXPECT_STR_EQ(a, b)`, `GDEX_EXPECT_STR_CONTAINS(h, n)` | string comparisons |
| `GDEX_EXPECT_NULL(p)`, `GDEX_EXPECT_NOT_NULL(p)` | pointer checks |
| `GDEX_FAIL(msg)`, `GDEX_ABORT_TEST(msg)` | unconditional failure / abort the test |
| `GDEX_SKIP(msg)` | record the test as skipped for a runtime reason and stop the body |

`GDEX_TEST_T(suite, name, tags)` registers with tags — `TAG_UNIT`, `TAG_INTEGRATION`,
`TAG_ASYNC`, `TAG_SLOW`, `TAG_FLAKY` (see `include/gdextest/config.h`). `TAG_FLAKY` tests
are retried until they pass. This repo's reference suites live in [`tests/`](tests/).

### Async / multi-frame tests

A test can suspend across engine frames and resume later — observe a frame counter, wait
for a signal, time a real operation. Register with `GDEX_TEST_ASYNC` and `co_await` a wait
on its context (the body is a C++20 coroutine — use `co_return;`, not `return;`):

```cpp
GDEX_TEST_ASYNC(async, engine_frames_advance) {
    godot::Engine *engine = godot::Engine::get_singleton();
    const int64_t before = static_cast<int64_t>(engine->get_process_frames());
    co_await ctx.await_frames(2);                 // suspend across 2 process frames
    GDEX_EXPECT_GE(static_cast<int64_t>(engine->get_process_frames()) - before, 2);
}
```

The runner pumps the live `SceneTree.process_frame` signal. Every wait has a safety net —
`await_frames(n, timeout_ms)` and `await_timer_ms(ms, timeout_ms)` fail the test if they
don't resolve in time, so a test that never resolves is red, never a hang. See
`docs/api-reference.md` → Async tests for details.

### Live-engine tests

To exercise the live engine (singletons, scene nodes, your registered classes), tag a test
`TAG_INTEGRATION` and include `gdextest/engine.h`:

```cpp
GDEX_TEST_T(engine, can_build_scene_graph, TAG_INTEGRATION) {
    godot::SceneTree *tree = gdextest::engine_tree(ctx);   // live engine tree
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(tree));
    godot::Node *child = memnew(godot::Node);
    child->set_name("temp");
    tree->get_root()->add_child(child);
    GDEX_EXPECT(child->get_parent() != nullptr);
    tree->get_root()->remove_child(child);
    memdelete(child);
}
```

`gdextest::engine_tree(ctx)` is the live `SceneTree`; `gdextest::engine_node(ctx)` is the
host `Node` the adapter ran from. They return null for pure (non-engine-triggered)
invocations, so guard with `GDEX_EXPECT_NOT_NULL` first. The engine handle stays an opaque
`void*` on `TestContext`, so the framework core is Godot-free.

## Testing your real extension

Two complementary ways to test your own code:

- **Compile it into the test build** — add your implementation files to
  `[gdextest.tests] sources` in `.gdextest.toml`. Fast, hermetic, no Godot load-time
  concerns.
- **Load the real extension in the fixture** — point at your built `.so` with
  `[gdextest.consumer_extension]` when a suite needs registered classes, editor plugins,
  or behavior only the actual extension exhibits:

  ```toml
  [gdextest.consumer_extension]
  library = "addons/my_extension/bin/libmy_extension.linux.editor.x86_64.so"
  ```

  Only one of `library` / `manifest` needs configuring — the other is derived
  automatically (the `.gdextension` is found next to the library, or the library is read
  from the manifest's `[libraries]` table). The fixture stages the extension under
  `addons/consumer/` and rewrites the manifest's library paths to match, so your real
  addon manifest works as-is.

## Running in CI

`gdextest test` forwards these flags after `--` (or you can invoke Godot directly — the
fixture lives at `build/gdextest/project`):

| Flag | Effect |
| --- | --- |
| `--gdextest-run` | run the suites and quit (the trigger; `GDX_RUN_TESTS=1` works too) |
| `--gdextest-filter=a.*,-a.slow` | comma-separated globs; `-` prefix excludes |
| `--gdextest-shard=k/n` | run shard k of n (stable hash assignment) |
| `--gdextest-shuffle[=seed]` | randomize order (fixed seed = reproducible) |
| `--gdextest-json=<path>` | write machine-readable results |
| `--gdextest-timeout-ms`, `--gdextest-isolate-timeout-sec`, `--gdextest-flaky-retries` | async budgets / flaky retries (from `[gdextest.test]`) |

CLI convenience: `gdextest test --junit=<path>` also writes JUnit XML (rendered as
annotations by GitHub Actions), and `gdextest report 'shard*.json' --json=m.json
--junit=m.xml` merges parallel shard results. Exit codes: `0` all passed, `1` any
failure/crash, `2` usage error.

## Commands

| Command | Effect |
| --- | --- |
| `gdextest test` | The one-command flow: config init + doctor + build + fixture + headless run |
| `gdextest init [--ci] [--force]` | Create the starter `.gdextest.toml` (and CI workflow) |
| `gdextest doctor` | Environment checks without building |
| `gdextest scaffold [--apply]` | Wire `SConstruct` permanently + generate entry/smoke suite |
| `gdextest list` | Build and list the selected tests |
| `gdextest report <paths…>` | Merge shard result JSON into one JSON/JUnit report |
| `gdextest clean` | Remove generated test output |

## Layout

| Path | Role |
| --- | --- |
| `include/gdextest/` | Public headers: registry, `TestContext`, assertions, tags, runner |
| `src/framework/` | Framework implementation (`registry.cpp`, `runner.cpp`, `host.cpp`) |
| `src/gdextest_entry.cpp` | GDExtension entry + `EditorPlugin` shell (test build only) |
| `src/support/adapter.cpp` | Per-extension adapter — the one file that knows your extension's setup |
| `tests/` | Framework self-tests + reference suites |
| `tools/` | CLI (`gdextest.py`), config, fixture generator |
| `run_tests.sh` | Build + run the framework's own suite, one command |
| `docs/` | Full documentation — [`docs/README.md`](docs/README.md) |

## How it works

- Suites register at static-init time in a pure-C++ registry (`include/gdextest/`); the
  core has **no Godot types**, so it's safe in static initializers.
- Only the runner (`src/framework/runner.cpp`) touches the engine boundary: it parses the
  `--gdextest-*` flags, runs the selected tests, writes human + JSON output, and exits via
  `SceneTree::quit(code)`.
- The fixture loads the test `.so` in editor mode (`--headless --editor`); the
  `EditorPlugin::_ready()` hook is the verified safe point to quit from. `user://` stays
  hermetic by pointing `XDG_DATA_HOME` at a per-run temp dir.
- After the build, the CLI runs an `ldd -r` preflight on the test library, so a suite
  calling code that isn't compiled into the test build fails fast with a pointer to the
  fix instead of a Godot load-time crash.

## Gotchas

- In `GDEX_TEST_ASYNC` bodies use `co_return;` — a bare `return;` is rejected by the
  compiler inside a coroutine.
- `--gdextest-list` alone doesn't trigger a run; pair it with `--gdextest-run`.
- Code your suite calls must be compiled into the test build (via `[gdextest.tests]
  sources`) or loaded through `[gdextest.consumer_extension]` — otherwise the run fails
  with undefined symbols at library load.
- `TAG_FLAKY` tests receive up to 3 retries by default; JSON includes a `retries` field.
- Exit code `2` (usage error) is emitted for malformed or unknown `--gdextest-*` options.
