# Consumer guide

How another GDExtension repo integrates gdextest. The reference consumer uses the same
reusable build and generated-fixture path described below.

## Model

There is no separate runner binary. The framework is compiled **into your test build**: a
test-only shared object containing the framework core, an entry point, your per-extension
adapter, and your suites. A fixture Godot project loads that `.so`; a headless run executes
the suites and exits with pass/fail. Release builds are untouched.

```
your repo/
  extern/gdextest/          # this framework (git submodule)
  src/…                     # your extension sources (untouched by the framework)
  tests/                    # your GDEX_TEST suites
  build/gdextest/project/    # generated fixture (disposable)
```

## 1. Pull in the framework

```bash
git submodule add <this-repo-url> extern/gdextest
git submodule update --init
```

The CLI is the `gdextest` wrapper script inside the submodule — run it from your repo root
as `./extern/gdextest/gdextest <command>`. All commands in this guide use that path.

Your build already vendors godot-cpp (every GDExtension does); the framework reuses your
`extern/godot-cpp` and expects a 4.5 binding set — it uses `EditorPlugin`,
`SceneTree::quit`, `OS::get_cmdline_args/get_cmdline_user_args`, and the 4.5
`GDExtensionBinding::InitObject` API. (The submodule's nested godot-cpp is only used by
the framework's own self-tests, so a plain `--init` is enough.)

## 2. Include layout

The framework follows the classic C++ library layout, so the include path stays clean and
predictable no matter where the submodule lands:

```
extern/gdextest/
  include/gdextest/     # public headers — the only files suites #include
  src/framework/        # implementation (.cpp) — compiled by the SConscript, never included
  SConscript            # reusable build integration (adds include/ to CPPPATH)
```

All public headers live under `include/gdextest/`, so a single `-I extern/gdextest/include`
entry resolves every framework include as a namespaced `gdextest/...` path — no digging
into the framework's source tree, no relative `../extern/gdextest/...` includes from your
suites:

```cpp
#include "gdextest/assert.h"
#include "gdextest/registry.h"
```

The reusable `SConscript` appends `include/` to the test target's `CPPPATH`, so the paths
resolve automatically. Only if you compile the framework sources yourself (bypassing the
SConscript) do you need to add `-I extern/gdextest/include` (or
`/I extern\gdextest\include` on MSVC) to your test target.

| Header | Purpose | Included by |
| --- | --- | --- |
| `gdextest/assert.h` | `GDEX_EXPECT_*` assertions, `GDEX_FAIL`, `GDEX_ABORT_TEST`, `GDEX_SKIP` | every suite |
| `gdextest/registry.h` | `GDEX_TEST` / `GDEX_TEST_T` / `GDEX_TEST_ASYNC*` registration, `TestRegistry`, `Filter` | every suite |
| `gdextest/engine.h` | live-engine accessors `gdextest::engine_tree(ctx)` / `engine_node(ctx)` — pulls in godot-cpp | engine-facing suites (with `TAG_INTEGRATION`) |
| `gdextest/async.h` | async-test coroutine machinery, `ctx.await_frames` / `ctx.await_timer_ms` | async suites (pulled in by `registry.h`) |
| `gdextest/context.h` | `TestContext`, `Failure`, teardowns, `track_object` / `track_ref` | advanced suites |
| `gdextest/config.h` | `Tag` enum, `kDefault*` budgets — the customization point | hosts that tune budgets |
| `gdextest/host.h` | `gdextest::configure_host({&start, &stop})` | extension init paths (§6) |
| `gdextest/runner.h` | runner entry points (`run_all_and_quit`, `run_sub_*`) — engine-boundary | self-tests, custom adapters |
| `gdextest/adapter.h` | `gdextest_adapter::maybe_run(godot::Node*)` contract | custom adapters (§7) |

Suite authors normally only touch `assert.h` and `registry.h`. The implementation files in
`src/framework/` are compiled into your test library by the SConscript; nothing in
`include/` is a copy or a symlink, so there is no second source of truth.

## 3. Write suites

Plain C++ files using the macros — see [api-reference.md](api-reference.md) for the full
surface:

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

Engine-facing tests run inside a real Godot process. Singletons, your registered classes,
and the live SceneTree are all reachable from a test body that opts in: tag the test
TAG_INTEGRATION and include `gdextest/engine.h`. Then gdextest::engine_tree(ctx) is the live
SceneTree and gdextest::engine_node(ctx) is the host Node. Pure-logic suites (no tag, no
engine.h) get null from both — the engine is opt-in:

```cpp
#include "gdextest/engine.h"

GDEX_TEST_T(my_extension, class_is_registered, TAG_INTEGRATION) {
    GDEX_EXPECT_NE(godot::OS::get_singleton()->get_processor_count(), 0);
    godot::SceneTree *tree = gdextest::engine_tree(ctx);   // live engine tree
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(tree));
}
```

**Async / multi-frame tests** (needs C++20 — the reusable `SConscript` compiles the test
target with `-std=c++20`). Register with `GDEX_TEST_ASYNC` and `co_await` engine waits; the
runner suspends and resumes the body across `process_frame` ticks:

```cpp
GDEX_TEST_ASYNC(my_extension, signal_settles_across_frames) {
    co_await ctx.await_frames(2);            // let the engine advance 2 frames
    GDEX_EXPECT(my_service->is_settled());
    co_return;
}
```

Every wait has a timeout (default 30 s per wait, 60 s per test) so a never-resolving
await fails the test instead of hanging CI. See `api-reference.md` → Async tests.

## 4. Run the quickstart

Once the framework submodule and a first suite are present, run the complete flow with one
command:

```bash
./extern/gdextest/gdextest test --json=results.json
```

`test` creates `.gdextest.toml` when it is missing, preserves it when it already exists,
and runs the doctor checks on every invocation before the build. The checks cover the
configuration, framework SConscript, Godot version, SCons, test source discovery, and any
configured consumer extension files. A failed check returns `2` before SCons or Godot is
started. Use `gdextest init --ci` when you want to generate the config and CI workflow
explicitly, or `gdextest doctor` to inspect the environment without running a build.
Godot is auto-discovered, so no `--godot` is needed.

After the preflight passes, the command builds the test-only library, generates the
fixture, warms the fixture cache, launches Godot headlessly, and returns `0` for a passing
run or `1` for test failures. Relative JSON paths are resolved against the consumer
repository's working directory.

**No `SConstruct` wiring is required.** If your build file doesn't call the framework
SConscript, `test` builds through a temporary injected copy (`SConstruct.gdextest`,
removed afterwards) — your build file is never modified. `gdextest scaffold --apply` makes
that wiring permanent (backing up `SConstruct` first) and generates `testsupport/entry.cpp`
from your TOML values — only needed for a custom entry point / plugin class; everything
else is covered by `gdextest test`.

## 5. Configure the consumer contract

The recommended configuration is structured by responsibility. Existing flat keys remain
supported for compatibility, but new projects should use this form:

```toml
[gdextest]
version = "1"
godot_version = "4.5"

[gdextest.tests]
sources = ["tests/**/*.cpp"]
exclude = ["tests/helpers/**"]

[gdextest.test]
timeout_ms = 30000          # per async wait
isolate_timeout_sec = 60    # whole-test async budget
flaky_retries = 3           # additional attempts for TAG_FLAKY tests

[gdextest.host]
mode = "editor" # editor or runtime
entry_symbol = "gdextest_library_init"
plugin_class = "GdextestPlugin" # native EditorPlugin registered by your entry
bootstrap = "tests/bootstrap.cpp" # optional

[gdextest.fixture]
directory = "build/gdextest/project"
project_name = "my extension tests"
native_extensions = []
assets = ["tests/fixtures/**"]
scan_timeout_ms = 20000     # how long the editor's first filesystem scan may take

[gdextest.output]
directory = "bin"
name = "libmy_extension_tests"

[gdextest.build]
args = [] # extra scons args, e.g. ["platform=windows", "target=editor", "arch=x86_64"]
```

The `[gdextest.test]` budgets are forwarded to the runner as `--gdextest-*` flags on every
CLI run — CI on slow machines or under ASan can raise them without rebuilding the
framework. `scan_timeout_ms` bounds the editor filesystem scan in the generated fixture
host (raise it for large repos / loaded CI).

The `test` preflight validates the configuration, framework path, Godot version, SCons,
discovered test sources, and any configured consumer extension files on every run. Run
`gdextest doctor --godot /path/to/Godot` directly when you want these diagnostics without
a build. `gdextest test` and `gdextest list` use the same configuration, so source discovery
and fixture settings cannot silently diverge.

The reusable `SConscript` loads this file itself, so the TOML is the single source of
truth for every flow: `gdextest test` sets a handful of `gdextest_*` environment variables
for the build (sources, host mode, bootstrap), and the SConscript treats them as overrides
layered on top of the TOML values. A value you set in the TOML is never silently ignored
by the build.

`host.mode = "editor"` generates the scan-safe `EditorPlugin` fixture and runs Godot with
`--headless --editor`. `host.mode = "runtime"` generates an autoload fixture and runs plain
`--headless`, which is appropriate for runtime-only extensions.

### Load your real extension alongside the tests

By default the code under test is whatever compiles into the test library (your
`[gdextest.tests]` sources). If a suite needs the *actual extension* loaded in the fixture
— registered classes, editor plugins, or engine behavior only the real `.so` exhibits —
point at it with `consumer_extension`:

```toml
[gdextest.consumer_extension]
library = "addons/my_extension/bin/libmy_extension.linux.editor.x86_64.so"
```

Only one of the two files needs to be configured; the other is derived automatically:

- **`library` set, `manifest` omitted** — the framework walks up from the library and uses
the unique `.gdextension` it finds (covers `addons/<name>/bin/` and `addons/<name>/`
layouts).
- **`manifest` set, `library` omitted** — the manifest's `[libraries]` table is read and
the first entry that resolves on disk is used.

If the search is ambiguous (several `.gdextension` files near the library), set both keys
explicitly. When nothing is configured but your project contains exactly one
`.gdextension`, `gdextest doctor` prints the exact TOML line to add. The fixture stages the
extension under `addons/consumer/` and rewrites the manifest's `[libraries]` paths to
point at that copy, so a real addon manifest works as-is.

## 6. Customize startup only when needed

If your extension needs services bootstrapped before the tests run, configure the host from
your extension's initialization code. Include `gdextest/host.h` and register ordinary
function pointers; no weak symbols or platform-specific linker behavior is required:

```cpp
#include "gdextest/host.h"

void start_test_services() { /* initialize consumer services */ }
void stop_test_services() { /* release consumer services */ }

void configure_gdextest_host() {
    gdextest::configure_host({&start_test_services, &stop_test_services});
}
```

Call `configure_gdextest_host()` from your extension's normal initialization path, after
Godot is initialized and before the test host is created. The default configuration is a
no-op, so consumers that need no setup provide nothing. The callback API is portable across
GCC, Clang, and MSVC; a custom `adapter` or `entry` remains available only when the default
host lifecycle itself is insufficient.

## 7. Write a custom adapter (optional)

If the default host is not enough, `adapter.cpp` is the **only file that should know your
extension's setup**. The contract lives in [`gdextest/adapter.h`](../include/gdextest/adapter.h)
— one declaration (`gdextest_adapter::maybe_run(godot::Node*)`) — so a custom adapter with
a wrong signature fails at compile time, not link time. Model it on
[`src/support/adapter.cpp`](../src/support/adapter.cpp) — ~40 lines by design:

```cpp
#ifdef GDEXTEST_ENABLED   // test build only

#include "gdextest/adapter.h"   // declares gdextest_adapter::maybe_run

#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/classes/scene_tree.hpp>

namespace gdextest { void run_all_and_quit(void *tree_node); }

namespace {
bool test_trigger_present() {
    godot::OS *os = godot::OS::get_singleton();
    if (!os) return false;
    if (os->has_environment("GDX_RUN_TESTS")) return true;
    // Check BOTH lists — args before "--" and after "--" (notes.md §3.2).
    return os->get_cmdline_args().has("--gdextest-run") ||
           os->get_cmdline_user_args().has("--gdextest-run");
}

void bootstrap() {
    // Start only the services your code under test needs.
    // (This repo has none yet; real hosts list theirs here.)
}
}  // namespace

namespace my_adapter {
void maybe_run(godot::Node *tree_node) {
    if (!test_trigger_present()) return;
    bootstrap();
    gdextest::run_all_and_quit(tree_node);
}
}  // namespace my_adapter

#endif // GDEXTEST_ENABLED
```

## 8. Add a custom entry point (optional)

Run `gdextest scaffold --apply` to generate `testsupport/entry.cpp` from a template,
using the `plugin_class` and `entry_symbol` from your TOML — no manual copy-and-rename.
(`testsupport/` sits outside the default `tests/**/*.cpp` suite glob so the entry compiles
exactly once.)
The generated file registers an `EditorPlugin` whose `_ready()` calls the framework
adapter. The generated fixture wrapper instantiates exactly the class named by
`[gdextest.host] plugin_class`, so keep the two in sync. Use the godot-cpp 4.5 entry API
exactly (the pre-4.5 form does not compile):

```cpp
extern "C" {
GDExtensionBool GDE_EXPORT my_library_init(
        GDExtensionInterfaceGetProcAddress p_get_proc_address,
        const GDExtensionClassLibraryPtr p_library,
        GDExtensionInitialization *r_initialization) {
    godot::GDExtensionBinding::InitObject init_obj(p_get_proc_address, p_library, r_initialization);
    init_obj.register_initializer(&initialize_test_module);
    init_obj.register_terminator(&uninitialize_test_module);
    init_obj.set_minimum_library_initialization_level(godot::MODULE_INITIALIZATION_LEVEL_EDITOR);
    return init_obj.init();
}
}
```

The `.gdextension` manifest in your fixture project must set `entry_symbol` to this
function's name.

## 9. Create a custom fixture project (optional)

Copy [`testdata/project/`](../testdata/project/) and adapt. Three pieces:

**`project.godot`** — registers the extension and enables the plugin:

```ini
[native_extensions]
paths=["res://mytest.gdextension"]

[editor_plugins]
enabled=PackedStringArray("res://addons/gdextest/plugin.cfg")
```

**`mytest.gdextension`** — points at your test `.so`. One `linux.debug.x86_64` entry is
enough; editor builds carry the `debug` feature tag, so it matches `--headless --editor`
runs too:

```ini
[configuration]
entry_symbol = "my_library_init"
compatibility_minimum = "4.5"

[libraries]
linux.debug.x86_64 = "res://bin/libmytest-test.linux.template_debug.x86_64.so"
```

**`addons/gdextest/plugin.cfg` + `plugin.gd`** — the plugin script must `extend
EditorPlugin` directly (extending your native plugin class is rejected by the plugin
manager). It instantiates the native plugin once the editor filesystem scan has finished —
quitting earlier races the scan thread and can crash the editor (`testing/notes.md` §5):

```gdscript
@tool
extends EditorPlugin

const SCAN_TIMEOUT_MS := 20000
var test_plugin: Node
var _start_ms := 0

func _ready() -> void:
    _start_ms = Time.get_ticks_msec()
    get_tree().process_frame.connect(_on_frame)

func _on_frame() -> void:
    var fs := EditorInterface.get_resource_filesystem()
    if fs.is_scanning() and Time.get_ticks_msec() - _start_ms < SCAN_TIMEOUT_MS:
        return
    get_tree().process_frame.disconnect(_on_frame)
    test_plugin = MyTestPlugin.new()
    add_child(test_plugin)

func _exit_tree() -> void:
    if get_tree() and get_tree().process_frame.is_connected(_on_frame):
        get_tree().process_frame.disconnect(_on_frame)
    if test_plugin:
        remove_child(test_plugin)
        test_plugin.queue_free()
        test_plugin = null
```

## 10. Run in CI

```bash
./extern/gdextest/gdextest test --json=results.json --junit=results.xml
```

Exit code `0` = green, `1` = red — map it straight to your pipeline. `--junit` converts the
run's JSON to JUnit XML, which GitHub Actions and other CI surfaces render as inline
annotations. For parallel CI use `--gdextest-shard=k/n` (stable assignment, disjoint
shards) per job, then merge the shard documents:

```bash
./extern/gdextest/gdextest report 'shard*.json' --json=merged.json --junit=merged.xml
```

`report` exits `1` when any merged test failed or crashed. `user://` is kept hermetic by the
CLI itself (it wipes `build/gdextest/user-data` before every run). See
[cli.md](cli.md) for the full flag reference.

## Troubleshooting

- **Editor hangs on `--headless --editor`:** the run isn't triggering — no `--gdextest-run`
  / `GDX_RUN_TESTS`, or your adapter isn't being called. Check the plugin is enabled in
  `project.godot` and the `.gdextension` entry symbol matches your `init` function.
- **Editor crashes on shutdown:** the run happened before the filesystem scan finished —
  keep the `is_scanning()` deferral in `plugin.gd`.
- **`Script inherits from native type … can't be assigned to EditorPlugin`:** the plugin
  script must extend `EditorPlugin` directly, not your native plugin class.
- **Link errors with `-fno-exceptions`:** the reusable `SConscript` adds `-fexceptions`
  to the test target automatically, so this only applies if you compile the framework
  sources yourself (bypassing the SConscript) — then add `-fexceptions` to the test
  target's `CXXFLAGS`.
- **Godot errors on a library/manifest name you no longer use** (e.g. an old
  `[gdextest.output] name`): the fixture was reused and stale `.gdextension` / `.so`
  files lingered — the editor scans every `.gdextension` it finds. Run `gdextest clean`
  to regenerate the fixture from scratch (regeneration now also removes stale files
  itself).
- **Test build fails to link with `cannot find -lgodot-cpp...`:** your `SConstruct` sets
  `CPPPATH` / `LIBPATH` with root-relative strings (e.g. `extern/godot-cpp/bin`). The
  framework SConscript rebases those to your project root automatically, so this is
  normally a non-issue — but if you compile the framework sources yourself (bypassing
  the SConscript), anchor the paths with `#` (`#extern/godot-cpp/bin`, `#src`, …) — the
  godot-cpp convention — so the build resolves them from any directory.
