# gdextest — GDExtension testing framework

A C++ testing framework for [Godot](https://godotengine.org) GDExtensions that runs your
suites **inside a headless Godot binary**: build once, run `godot --headless`, and read
pass/fail from the exit code. Suites are written in plain C++ with googletest-style macros,
can exercise both pure logic and live engine APIs (singletons, your own registered classes,
`Variant`/`String` round-trips, …), and are CI-friendly via JSON output and test
filtering/sharding.

> **Status:** Milestones A–C are complete: the framework core, portable `HostConfig`,
> reference fixture, headless execution, structured configuration, diagnostics, JSON
> output, the CLI-driven external-consumer flow, and async / multi-frame tests are
> working on Godot 4.5.

---

## Quickstart (this repo)

Prerequisites: `scons`, a C++17 toolchain, and a Godot **4.5** binary (this repo pins
`extern/godot-cpp` to the `4.5` branch).

```bash
# one command: build, generate the fixture, and run headless
GODOT=/path/to/Godot_v4.5-stable_linux.x86_64 ./gdextest test
```

The CLI also supports `./gdextest init`, `./gdextest doctor`, `./gdextest list`, and
`./gdextest clean`.

Or step by step:

```bash
scons platform=linux target=template_debug tests=true      # builds + generates build/gdextest/project
godot --headless --editor --path build/gdextest/project -- --gdextest-run
```

You'll see a summary like `== gdextest: 34 passed, 0 failed, 1 skipped ==` and the shell
exit code tells you the result: **0** = all passed (skips do not fail the run),
**1** = ≥1 failure, **2** = usage error.

## Writing tests

Suites are C++ files using the `GDX_TEST` macro and the `GDX_EXPECT_*` assertions. A test
body receives a `TestContext&` named `ctx` (injected by the runner), so macros reference it
automatically:

```cpp
#include "framework/assert.h"
#include "framework/registry.h"

GDX_TEST(string_utils, trim_strips_both_ends) {
    GDX_EXPECT_STR_EQ(trim("  hello  "), "hello");
}

GDX_TEST(counter, bump_increments) {
    Counter c;
    c.bump();
    GDX_EXPECT_EQ(c.value(), 1);
}
```

Assertions record failures and keep going (they never throw), so one test reports every
failing check:

| Macro | Checks |
| --- | --- |
| `GDX_EXPECT(cond)`, `GDX_EXPECT_TRUE/FALSE` | boolean conditions |
| `GDX_EXPECT_EQ/NE/LT/LE/GT/GE(a, b)` | comparisons with value formatting |
| `GDX_EXPECT_NEAR(a, b, eps)` | floating-point tolerance |
| `GDX_EXPECT_STR_EQ(a, b)`, `GDX_EXPECT_STR_CONTAINS(h, n)` | string comparisons |
| `GDX_EXPECT_NULL(p)`, `GDX_EXPECT_NOT_NULL(p)` | pointer checks |
| `GDX_FAIL(msg)`, `GDX_ABORT_TEST(msg)` | unconditional failure / abort the test |
| `GDX_SKIP(msg)` | record the test as skipped for a runtime reason and stop the body |

`GDX_TEST_T(suite, name, tags)` registers with tags (`TAG_UNIT`, `TAG_INTEGRATION`,
`TAG_SLOW`, `TAG_FLAKY`, … — see `src/framework/config.h`). Tag names resolve bare, so write
`GDX_TEST_T(engine, spins_up, TAG_INTEGRATION)` exactly as shown. This repo's reference
suites live in [`tests/`](tests/).

### Async / multi-frame tests

A test can suspend across engine frames and resume later — e.g. to observe a frame
counter advance, wait for a signal to settle, or time a real operation. Register it
with `GDX_TEST_ASYNC` (tagged `TAG_ASYNC`; `GDX_TEST_ASYNC_T(suite, name, tags)` for
extra tags) and `co_await` a wait on its context. The body is a C++20 coroutine; use
`co_return;` instead of a bare `return;`:

```cpp
GDX_TEST_ASYNC(async, engine_frames_advance) {
    godot::Engine *engine = godot::Engine::get_singleton();
    const int64_t before = static_cast<int64_t>(engine->get_process_frames());
    co_await ctx.await_frames(2);                 // suspend across 2 process frames
    GDX_EXPECT_GE(static_cast<int64_t>(engine->get_process_frames()) - before, 2);

    const int64_t start = godot::Time::get_singleton()->get_ticks_msec();
    co_await ctx.await_timer_ms(100);             // or wait on wall-clock time
    GDX_EXPECT_GE(godot::Time::get_singleton()->get_ticks_msec() - start, 100);
}
```

The runner pumps the live `SceneTree.process_frame` signal: sync tests still run inline,
async tests are resumed one at a time in declaration order. Every wait has a safety
net — `ctx.await_frames(n, timeout_ms)` and `ctx.await_timer_ms(ms, timeout_ms)` fail
the test if the wait does not resolve in time (default `kDefaultTimeoutMs` = 30 s;
`kDefaultIsolateTimeoutSec` = 60 s bounds the whole test), so a test that never
resolves is red, never a hang. See `docs/api-reference.md` → Async tests for details.

### Live-engine tests

Pure-logic tests never touch the engine and need nothing else. To exercise the live Godot
engine (singletons, creating/removing scene nodes, your registered classes), tag a test
`TAG_INTEGRATION` and include `framework/engine.h`. The runner exposes the live `SceneTree`
on the test's context:

```cpp
#include "framework/assert.h"
#include "framework/engine.h"
#include "framework/registry.h"

GDX_TEST_T(engine, can_build_scene_graph, TAG_INTEGRATION) {
    godot::SceneTree *tree = gdextest::engine_tree(ctx);   // live engine tree
    GDX_EXPECT_NOT_NULL(static_cast<void *>(tree));
    godot::Node *child = memnew(godot::Node);
    child->set_name("temp");
    tree->get_root()->add_child(child);
    GDX_EXPECT(child->get_parent() != nullptr);
    tree->get_root()->remove_child(child);
    memdelete(child);
}
```

`gdextest::engine_tree(ctx)` is the live `SceneTree`; `gdextest::engine_node(ctx)` is the
host `Node` the adapter ran from. These return null for pure (non-engine-triggered)
invocations, so guard with `GDX_EXPECT_NOT_NULL` before dereferencing. Because the engine
handle is an opaque `void*` on `TestContext`, the framework core stays Godot-free.

## Command-line flags

Pass them **after `--`** so they arrive as user args (the trigger is detected in both arg
lists; the options are read from the user list):

| Flag | Effect |
| --- | --- |
| `--gdextest-run` | trigger: run the suites and quit (or `GDX_RUN_TESTS=1` env var) |
| `--gdextest-list` | print the selected tests without running (requires a trigger) |
| `--gdextest-filter=a.*,-a.slow` | comma-separated globs; `-` prefix excludes (googletest-style) |
| `--gdextest-shard=k/n` | run shard k of n (stable hash assignment) |
| `--gdextest-shuffle[=seed]` | randomize order (fixed seed = reproducible) |
| `--gdextest-json=<path>` | write machine-readable results to a file |

Async tests need the engine: run them through the trigger (the fixture's
`EditorPlugin`), where the runner can pump frames. The `self` suite also verifies the
async machinery headlessly with a simulated frame clock.

Example:

```bash
godot --headless --editor --path testdata/project -- \
    --gdextest-run --gdextest-filter=counter.* --gdextest-json=results.json
```

## Using gdextest in your own extension

The framework is a thin layer around your existing GDExtension build — there is no separate
runner binary to install. You pull in the framework sources, compile them **into your test
build**, and drive them through a tiny per-extension adapter. The CLI owns the whole loop:
config, build, fixture generation, headless run, and JSON results.

1. **Add the framework to your repo** (git submodule, mirroring the `extern/godot-cpp`
   pattern used here):

   ```bash
   git submodule add <this repo> extern/gdextest
   git submodule update --init --recursive   # also pulls extern/gdextest/extern/godot-cpp
   ```

2. **Generate the starter config** — `./gdextest init` writes a `.gdextest.toml` that
   matches your layout (add `--ci` to also drop in a GitHub Actions workflow):

   ```bash
   ./gdextest init --ci
   ```

3. **Write your suites** with `GDX_TEST(...)` and the assertion macros (above). Nothing
   else is needed for pure-logic tests; tag `TAG_INTEGRATION` and include
   `framework/engine.h` to reach the live engine.

4. **Validate the environment once** — `./gdextest doctor` checks the config, framework
   path, Godot version, SCons, and discovered test sources:

   ```bash
   ./gdextest doctor --godot /path/to/Godot
   ```

5. **Build and run** — one command builds the test library, generates the disposable
   fixture, runs headless, and maps the exit code to your pipeline:

   ```bash
   ./gdextest test --godot /path/to/Godot --json=results.json
   ```

   Exit code `0` = green, `1` = red. Write `--json=results.json` for CI artifacts and use
   `--shard=k/n` to parallelize.

6. **Customize only when needed** — everything lives in `.gdextest.toml` (test sources,
   host mode, fixture, output name). For extension-specific startup, register ordinary
   function pointers with `gdextest::configure_host({&start, &stop})` from your
   initialization path — no weak symbols or platform-specific linker behavior. A custom
   `entry`/`adapter` remains available for the rare case the default host lifecycle isn't
   enough.

Under the hood, the CLI drives the reusable [`SConscript`](SConscript), which supplies the
generic entry point and adapter, compiles the framework plus your suites into a test-only
shared object with `GDEXTEST_ENABLED` defined, and generates the fixture project. If you
prefer to wire it into your existing `SConstruct` directly, the minimal call is:

```python
lib = env.SConscript(
    "extern/gdextest/SConscript",
    variant_dir="build/gdextest", duplicate=0,
    exports={"env": env, "gdextest": {
        "enabled": env.get("tests", False),
        "suites": Glob("tests/*.cpp"),
    }},
)
if lib:
    Default(lib)
```

No fixture files, manifest, plugin wrapper, or library symlink need to be copied into the
repository — they're all generated.


## How it works

- Suites are registered at static-init time in a pure-C++ registry (`src/framework/`); the
  core has **no Godot types** so it's safe in static initializers.
- Only the runner (`src/framework/runner.cpp`) touches the engine boundary: it parses the
  `--gdextest-*` flags, runs the selected tests synchronously, writes human + JSON output,
  and exits via `SceneTree::quit(code)`.
- The fixture project loads the test `.so` in **editor mode** (`--headless --editor`); the
  `EditorPlugin::_ready()` hook is the verified safe point to quit from (an autoload hook
  hangs — see `docs/testing/notes.md` §3.3).
- `user://` is kept hermetic by pointing `XDG_DATA_HOME` at a temp dir (notes.md §3.1).

## Layout

| Path | Role |
| --- | --- |
| `src/framework/` | Pure C++ core: registry, `TestContext`, assertions, tags, runner |
| `src/gdextest_entry.cpp` | GDExtension entry + `EditorPlugin` shell (test build only) |
| `src/support/adapter.cpp` | Per-extension adapter — the one file that knows your wiring |
| `tests/` | Framework self-tests + reference suites |
| `tools/generate_fixture.py` | Generates the disposable headless Godot fixture |
| `build/gdextest/project/` | Generated fixture project (not committed) |
| `run_tests.sh` | Build + wire + headless run, one command |
| `docs/` | Full documentation (architecture, API reference, CLI, consumer guide — see [`docs/README.md`](docs/README.md)) |

## Gotchas

- In `GDX_TEST_ASYNC` bodies use `co_return;` — a bare `return;` is rejected by the
  compiler inside a coroutine.
- The editor plugin script must `extend EditorPlugin` directly — extending the native
  `GdextestPlugin` is rejected by the plugin manager.
- The run must be deferred until `EditorFileSystem.is_scanning()` is false, or the editor
  can crash on shutdown (notes.md §5).
- `--gdextest-list` alone doesn't trigger a run; pair it with `--gdextest-run`.
- Exit code 2 (usage error) is emitted for malformed or unknown `--gdextest-*` options.
