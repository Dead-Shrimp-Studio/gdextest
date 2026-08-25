# gdextest — GDExtension testing framework

A C++ testing framework for [Godot](https://godotengine.org) GDExtensions that runs your
suites **inside a headless Godot binary**: build once, run `godot --headless`, and read
pass/fail from the exit code. Suites are written in plain C++ with googletest-style macros,
can exercise both pure logic and live engine APIs (singletons, your own registered classes,
`Variant`/`String` round-trips, …), and are CI-friendly via JSON output and test
filtering/sharding.

> **Status:** the framework core, runner, reference fixture, headless execution, and the
> reusable consumer [`SConscript`](SConscript) are working (15 self + reference tests green
> on Godot 4.5). Roadmap: [`.plans/gdextension-testing-framework.md`](.plans/gdextension-testing-framework.md).

---

## Quickstart (this repo)

Prerequisites: `scons`, a C++17 toolchain, and a Godot **4.5** binary (this repo pins
`extern/godot-cpp` to the `4.5` branch).

```bash
# one command: build, generate the fixture, and run headless
GODOT=/path/to/Godot_v4.5-stable_linux.x86_64 ./gdxtest test
```

The CLI also supports `./gdxtest init`, `./gdxtest list`, and `./gdxtest clean`.

Or step by step:

```bash
scons platform=linux target=template_debug tests=true      # builds + generates build/gdxtest/project
godot --headless --editor --path build/gdxtest/project -- --gdxtest-run
```

You'll see a summary like `== gdextest: 19 passed, 0 failed, 1 skipped ==` and the shell
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
| `--gdxtest-run` | trigger: run the suites and quit (or `GDX_RUN_TESTS=1` env var) |
| `--gdxtest-list` | print the selected tests without running (requires a trigger) |
| `--gdxtest-filter=a.*,-a.slow` | comma-separated globs; `-` prefix excludes (googletest-style) |
| `--gdxtest-shard=k/n` | run shard k of n (stable hash assignment) |
| `--gdxtest-shuffle[=seed]` | randomize order (fixed seed = reproducible) |
| `--gdxtest-json=<path>` | write machine-readable results to a file |

Example:

```bash
godot --headless --editor --path testdata/project -- \
    --gdxtest-run --gdxtest-filter=counter.* --gdxtest-json=results.json
```

## Using gdextest in your own extension

The framework is a thin layer around your existing GDExtension build — there is no separate
runner binary to install. You pull in the framework sources, compile them **into your test
build**, and drive them through a tiny per-extension adapter.

1. **Add the framework to your repo** (git submodule, mirroring the `extern/godot-cpp`
   pattern used here): `git submodule add <this repo> extern/gdextest`.

2. **Write your suites** with `GDX_TEST(...)` and the assertion macros (above). Nothing
   else is needed for pure-logic tests.3. **Build with the reusable `SConscript`** — it supplies the generic entry point and
   adapter, compiles the framework plus your suites into a test-only shared object, and
   generates a disposable fixture project. The minimal configuration is:

   ```python
   lib = env.SConscript(
       "extern/gdextest/SConscript",
       variant_dir="build/gdxtest", duplicate=0,
       exports={"env": env, "gdxtest": {
           "enabled": env.get("tests", False),
           "suites": Glob("tests/*.cpp"),
       }},
   )
   if lib:
       Default(lib)
   ```

4. **Run the generated fixture**: `godot --headless --editor --path
   build/gdxtest/project -- --gdxtest-run --gdxtest-json=results.json` and map the exit
   code to your pipeline. No fixture files, manifest, plugin wrapper, or library symlink
   need to be copied into the repository.

5. **Customize only when needed**: provide `entry`, `adapter`, `fixture_dir`,
   `entry_symbol`, `project_name`, or `native_extensions` in the `gdxtest` exports when
   the extension needs custom startup or additional native libraries. The default adapter
   is intentionally a no-op bootstrap; extension-specific initialization remains an
   explicit opt-in override.


> The `SConscript` wiring is done; the fixture project is still copy-the-template — this
> repo's `testdata/project/` is the reference.

## How it works

- Suites are registered at static-init time in a pure-C++ registry (`src/framework/`); the
  core has **no Godot types** so it's safe in static initializers.
- Only the runner (`src/framework/runner.cpp`) touches the engine boundary: it parses the
  `--gdxtest-*` flags, runs the selected tests synchronously, writes human + JSON output,
  and exits via `SceneTree::quit(code)`.
- The fixture project loads the test `.so` in **editor mode** (`--headless --editor`); the
  `EditorPlugin::_ready()` hook is the verified safe point to quit from (an autoload hook
  hangs — see `docs/testing/notes.md` §3.3).
- `user://` is kept hermetic by pointing `XDG_DATA_HOME` at a temp dir (notes.md §3.1).

## Layout

| Path | Role |
| --- | --- |
| `src/framework/` | Pure C++ core: registry, `TestContext`, assertions, tags, runner |
| `src/gdx_test_entry.cpp` | GDExtension entry + `EditorPlugin` shell (test build only) |
| `src/support/adapter.cpp` | Per-extension adapter — the one file that knows your wiring |
| `tests/` | Framework self-tests + reference suites |
| `tools/generate_fixture.py` | Generates the disposable headless Godot fixture |
| `build/gdxtest/project/` | Generated fixture project (not committed) |
| `run_tests.sh` | Build + wire + headless run, one command |
| `docs/` | Full documentation (architecture, API reference, CLI, consumer guide — see [`docs/README.md`](docs/README.md)) |
| `.plans/` | Milestone plan |

## Gotchas

- The editor plugin script must `extend EditorPlugin` directly — extending the native
  `GdxTestPlugin` is rejected by the plugin manager.
- The run must be deferred until `EditorFileSystem.is_scanning()` is false, or the editor
  can crash on shutdown (notes.md §5).
- `--gdxtest-list` alone doesn't trigger a run; pair it with `--gdxtest-run`.
- Exit code 2 (usage error) is emitted for malformed or unknown `--gdxtest-*` options.
