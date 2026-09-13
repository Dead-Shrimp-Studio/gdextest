# gdextest — GDExtension testing framework

[![ci](https://github.com/Dead-Shrimp-Studio/gdextension-test-framework/actions/workflows/ci.yml/badge.svg?event=push)](https://github.com/Dead-Shrimp-Studio/gdextension-test-framework/actions/workflows/ci.yml)

A C++ testing framework for [Godot](https://godotengine.org) GDExtensions. You write googletest-style suites in plain C++. gdextest compiles them into a test-only shared object, loads it in a real (headless) Godot process through a generated fixture project, and reports pass/fail through the process exit code. No separate runner binary, no scripting layer, no changes to your release build.

**Website:** [deadshrimpstudio.com/projects/gdextest](https://deadshrimpstudio.com/projects/gdextest/)

## Why gdextest

- **Tests live in the engine.** Integration tests reach singletons, `ClassDB`, and the live scene tree directly. Pure-logic tests need no engine at all.
- **Multi-frame tests.** C++20 coroutines suspend across engine frames: `co_await ctx.await_frames(2)`. Timeouts bound every wait, so a stalled test fails instead of hanging CI.
- **Signal monitoring.** Watch any object's signals, count emissions, and inspect the arguments of every emission.
- **Leak checks.** Track Godot objects and `RefCounted` references. The framework fails the test when they survive teardown.
- **Lifecycle hooks.** `configure_host` callbacks plus any number of `ExtensionAdapter`s cover extension-specific startup and shutdown without touching the runner.
- **One command.** `gdextest test` builds, generates the fixture, launches Godot, and quits with `0` or `1`. It works on a fresh clone without touching your `SConstruct`.
- **CI-ready output.** JSON and JUnit XML, plus a clean GoogleTest-style console report with colored pass/fail lines — rendered by the CLI after the engine exits, so Godot's own output never mangles it. Filtering, stable-hash sharding, seeded shuffling, and shard merging are built in.
- **Two host modes.** Editor mode hooks a scan-safe `EditorPlugin`; runtime mode uses a plain autoload for runtime-only extensions.
- **Zero release footprint.** Everything compiles only when `GDEXTEST_ENABLED` is defined. Release builds never see it.

## Quickstart

```bash
git submodule add <this-repo-url> extern/gdextest
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

One command does the whole flow. It writes a starter `.gdextest.toml` when none exists (it never overwrites one), runs the doctor preflight (config, Godot, SCons, godot-cpp version, test sources), builds the test library, generates and warms the fixture, launches Godot headless, prints the summary, and removes the disposable fixture afterwards. Exit codes: `0` all passed, `1` any failure or crash, `2` usage or environment error.

**No `SConstruct` wiring required.** When your build file does not call the framework SConscript, the build runs through a temporary injected copy that is deleted afterwards. `gdextest scaffold --apply` makes the wiring permanent (a `.bak` backup is written first) and generates `testsupport/entry.cpp` from your config values.

Prerequisites: SCons, a C++20 toolchain, Python 3, and a Godot 4.5 binary. Godot is auto-discovered (project tree, ancestor directories, `$HOME`, `PATH`).

## Writing tests

A test body receives a `TestContext&` named `ctx`. Assertion macros find it by name:

```cpp
GDEX_TEST(counter, bump_increments) {
    Counter c;
    c.bump();
    GDEX_EXPECT_EQ(c.value(), 1);
}
```

A failed expectation records a failure and continues, so one test reports every failing check. The macro set:

| Family | Macros |
| --- | --- |
| Boolean and comparison | `GDEX_EXPECT`, `GDEX_EXPECT_TRUE/FALSE`, `GDEX_EXPECT_EQ/NE/LT/LE/GT/GE`, `GDEX_EXPECT_NEAR` |
| Pointers | `GDEX_EXPECT_NULL`, `GDEX_EXPECT_NOT_NULL` |
| Strings (`std::string`, `const char*`, `godot::String` mix freely) | `GDEX_EXPECT_STR_EQ/NE/CONTAINS/STARTS_WITH/ENDS_WITH/EMPTY/NOT_EMPTY` |
| Exceptions | `GDEX_EXPECT_THROW`, `GDEX_EXPECT_NO_THROW`, `GDEX_EXPECT_ANY_THROW` |
| Fatal (stop the test) | `GDEX_ASSERT_TRUE/FALSE/EQ/NE/NULL/NOT_NULL`, `GDEX_ABORT_TEST` |
| Flow control | `GDEX_FAIL`, `GDEX_FAIL_IF`, `GDEX_FAIL_UNLESS`, `GDEX_SKIP` |

Tags (`TAG_UNIT`, `TAG_INTEGRATION`, `TAG_ASYNC`, `TAG_SLOW`, `TAG_FLAKY`) mark test categories. `TAG_FLAKY` tests get up to `flaky_retries` extra attempts (default 3). Cleanup callbacks (`ctx.add_teardown`), skip handling, and leak tracking are covered in [Writing tests](docs/writing-tests.md).

### Async / multi-frame tests

```cpp
GDEX_TEST_ASYNC(async, engine_frames_advance) {
    godot::Engine *engine = godot::Engine::get_singleton();
    const int64_t before = static_cast<int64_t>(engine->get_process_frames());
    co_await ctx.await_frames(2);                 // suspend across 2 process frames
    GDEX_EXPECT_GE(static_cast<int64_t>(engine->get_process_frames()) - before, 2);
}
```

The body is a C++20 coroutine and must end with `co_return;`. The runner pumps `SceneTree.process_frame` and resumes the body when the wait resolves. Every wait carries a timeout (default 30 s per wait, 60 s per test), so a test that never resolves is red, never a hang. See [Async tests](docs/async-tests.md).

### Live-engine tests

Tag a test `TAG_INTEGRATION` and include `gdextest/engine.h` to reach the live engine:

```cpp
GDEX_TEST_T(engine, can_build_scene_graph, TAG_INTEGRATION) {
    godot::SceneTree *tree = gdextest::engine_tree(ctx);   // live engine tree
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(tree));
    godot::Node *child = memnew(godot::Node);
    ctx.track_object(child);
    tree->get_root()->add_child(child);
    tree->get_root()->remove_child(child);
    memdelete(child);
}
```

Both accessors return null outside engine-triggered runs, so guard before use. For signal behavior, `ctx.signals()` returns a per-test `SignalMonitor` that counts emissions and records their arguments. See [Engine integration](docs/engine-integration.md).

## Testing your real extension

Two complementary ways:

- **Compile it into the test build.** Add your implementation files to `[gdextest.tests] sources`. Fast and hermetic. The CLI runs an `ldd -r` preflight (Linux) after the build, so code that is missing from the test build fails fast with the symbol list instead of a Godot load-time crash.
- **Load the real extension in the fixture.** Point at your built library with `[gdextest.consumer_extension]` when a suite needs registered classes, editor plugins, or behavior only the real `.so` exhibits:

  ```toml
  [gdextest.consumer_extension]
  library = "addons/my_extension/bin/libmy_extension.linux.editor.x86_64.so"
  ```

  Only one of `library` / `manifest` needs configuring; the other is derived automatically. The fixture stages the extension under `addons/consumer/` and rewrites the manifest's library paths, so a real addon manifest works as-is.

## Running in CI

```bash
./extern/gdextest/gdextest test --json=results.json --junit=results.xml
```

The exit code gates the pipeline. JUnit XML renders as inline annotations on GitHub Actions and other CI surfaces. `gdextest init --ci` writes the workflow for you. For parallel runs:

```bash
./extern/gdextest/gdextest test --shard=0/4 --json=shard0.json
./extern/gdextest/gdextest report 'shard*.json' --json=merged.json --junit=merged.xml
```

Shard assignment is a stable hash, so the same test always lands in the same shard and shards stay disjoint. `report` exits `1` when any merged test failed, so the merge step gates too.

## Commands

| Command | Effect |
| --- | --- |
| `gdextest test` | The one-command flow: config init + doctor + build + fixture + headless run |
| `gdextest init [--ci] [--force]` | Create the starter `.gdextest.toml` (and CI workflow) |
| `gdextest doctor` | Environment checks without building |
| `gdextest scaffold [--apply]` | Wire `SConstruct` permanently + generate entry/smoke suite |
| `gdextest list` | Build and list the selected tests (needs a run trigger) |
| `gdextest report <paths…>` | Merge shard result JSON into one JSON/JUnit report |
| `gdextest clean` | Remove generated test output |

Runner flags (`--gdextest-run`, `--gdextest-filter=`, `--gdextest-shard=k/n`, `--gdextest-shuffle[=seed]`, `--gdextest-json=`, and the budget flags) are forwarded by `test`. See the [CLI reference](docs/cli.md) for every command, flag, and exit code.

## Documentation

The full documentation lives in [`docs/`](docs/index.md):

| Page | Contents |
| --- | --- |
| [Getting started](docs/getting-started.md) | Install, first suite, first run, CI |
| [Writing tests](docs/writing-tests.md) | Assertions, tags, teardowns, skipping, resource tracking |
| [Async tests](docs/async-tests.md) | Multi-frame tests, waits, timeouts, budgets |
| [Engine integration](docs/engine-integration.md) | Live-engine tests and `SignalMonitor` |
| [Architecture](docs/architecture.md) | Design, layering rules, adapters, run lifecycle |
| [CLI reference](docs/cli.md) | Commands, flags, exit codes, output formats |
| [Configuration](docs/configuration.md) | The full `.gdextest.toml` reference |
| [Consumer guide](docs/consumer-guide.md) | End-to-end integration, adapters, custom fixtures |
| [API reference](docs/api-reference.md) | The complete public API, header by header |
| [Troubleshooting](docs/troubleshooting.md) | Known failure modes and their fixes |

## How it works

- Suites register in a pure C++ registry at static-initialization time. The core never touches Godot types there.
- Only a small engine boundary touches godot-cpp: the runner, `engine.h`, `strings.h`, `signals.h`, and the entry/adapter sources.
- The fixture loads the test library in editor mode (`--headless --editor`). The plugin waits for the editor's first filesystem scan, then the adapter checks the trigger (`--gdextest-run` or `GDX_RUN_TESTS`) and starts the run.
- The runner writes the JSON results document before anything else, then exits through `SceneTree::quit(code)` — `0` pass, `1` failure, `2` usage error. Its own console lines are marker-prefixed (`GDX_TEST_OUTPUT:`) and the CLI renders the human report from the JSON after the engine exits, so Godot's banner and load chatter never interleave with test results.
- `user://` stays hermetic: the CLI wipes `build/gdextest/user-data` before every run and points `XDG_DATA_HOME` at it. The fixture project is disposable and removed after every run.

## Repository layout

| Path | Role |
| --- | --- |
| `include/gdextest/` | Public headers: registry, assertions, `TestContext`, async, signals, runner |
| `src/framework/` | Framework implementation (`registry.cpp`, `runner.cpp`, `host.cpp`, `signals.cpp`) |
| `src/gdextest_entry.cpp` | GDExtension entry + `EditorPlugin` shell (test build only) |
| `src/support/adapter.cpp` | Reference adapter: trigger detection, adapter dispatch, run start |
| `tests/` | Framework self-tests + reference suites |
| `tools/` | CLI (`gdextest.py`), config loading, fixture generator |
| `run_tests.sh` | Build + run this repository's own suite, one command |
| `docs/` | The documentation wiki — start at [`docs/index.md`](docs/index.md) |

## Requirements

- Godot **4.5** (the framework uses 4.5-only GDExtension APIs).
- SCons and a C++20 toolchain (coroutines are required for async tests).
- Python 3 for the CLI.

## License

See [LICENSE](LICENSE).
