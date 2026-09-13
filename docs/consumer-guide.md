---
title: "Consumer guide"
description: "End-to-end integration in another repository: build wiring, adapters, entry points, fixtures, CI."
order: 50
sidebar: "Reference"
draft: false
---

# Consumer guide

How another GDExtension repository integrates gdextest, from the first submodule to a parallel CI run.

## The model

There is no separate runner binary. The framework compiles **into your test build**: one test-only shared object containing the framework core, an entry point, the adapter, and your suites. A generated fixture Godot project loads that object. A headless run executes the suites and exits with pass/fail. Release builds are untouched.

```text
your repo/
  extern/gdextest/             # this framework (git submodule)
  src/...                      # your extension sources (untouched)
  tests/                       # your GDEX_TEST suites
  .gdextest.toml               # created on the first `gdextest test`
  build/gdextest/project/      # ephemeral fixture (generated per run, removed after)
  bin/                         # the built test library
```

## 1. Pull in the framework

```bash
git submodule add <this-repo-url> extern/gdextest
git submodule update --init
```

Every command in this guide runs from your repository root as `./extern/gdextest/gdextest <command>`.

Your build already vendors `godot-cpp`; the framework reuses it. The framework expects a 4.5 binding set. The submodule's nested `godot-cpp` copy is used only by the framework's own self-tests, so a plain `git submodule update --init` is enough.

## 2. Include layout

The framework uses the classic library layout:

```text
extern/gdextest/
  include/gdextest/     # public headers, the only files suites include
  src/framework/        # implementation, compiled by the SConscript
  SConscript            # reusable build wiring
```

All public headers live under `include/gdextest/`, so one include path resolves every framework include as a namespaced `gdextest/...` path:

```cpp
#include "gdextest/assert.h"
#include "gdextest/registry.h"
```

The reusable SConscript appends `include/` to the test target's `CPPPATH`. Only if you compile the framework sources yourself (bypassing the SConscript) do you add `-I extern/gdextest/include` (or `/I extern\gdextest\include` on MSVC).

| Header | Purpose |
| --- | --- |
| `gdextest/assert.h` | All assertion macros, `GDEX_FAIL*`, `GDEX_ABORT_TEST`, `GDEX_SKIP`. |
| `gdextest/registry.h` | `GDEX_TEST*` registration, `TestRegistry`, `Filter`. Pulls in `async.h`. |
| `gdextest/engine.h` | `engine_node(ctx)` / `engine_tree(ctx)` for live-engine tests. |
| `gdextest/signals.h` | `SignalMonitor` and `ctx.signals()`. |
| `gdextest/strings.h` | `to_std_string` overloads for mixed string assertions. |
| `gdextest/async.h` | Async-test coroutine machinery and the awaitables. |
| `gdextest/context.h` | `TestContext`, `Failure`, teardowns, resource tracking. |
| `gdextest/config.h` | Tag enum and budget defaults; the customization point. |
| `gdextest/host.h` | `configure_host` startup/shutdown callbacks. |
| `gdextest/runner.h` | Runner entry points; for self-tests and custom adapters. |
| `gdextest/adapter.h` | The `ExtensionAdapter` interface and registry. |

Suite authors normally need only `assert.h` and `registry.h`. The SConscript compiles the test target with C++20 and exceptions enabled.

## 3. Write suites

Plain C++ files with the macros. See [Writing tests](/projects/gdextest/docs/writing-tests) for the full surface:

```cpp
#include "gdextest/assert.h"
#include "gdextest/registry.h"
#include "my_extension/math_utils.h"   // your code under test

GDEX_TEST(math_utils, clamp_keeps_value_in_range) {
    GDEX_EXPECT_EQ(clamp(5, 0, 10), 5);
    GDEX_EXPECT_EQ(clamp(-1, 0, 10), 0);
}
```

For engine-facing tests, tag them and include `engine.h`. For frame-dependent behavior, use `GDEX_TEST_ASYNC`. See [Engine integration](/projects/gdextest/docs/engine-integration) and [Async tests](/projects/gdextest/docs/async-tests).

**The code under test must be in the test build.** Everything a suite calls must compile into the test library (via `[gdextest.tests] sources`) or load through `[gdextest.consumer_extension]`. Otherwise the library carries undefined symbols; the CLI catches them with `ldd -r` right after the build.

## 4. Run the quickstart

```bash
./extern/gdextest/gdextest test --json=results.json
```

`test` creates `.gdextest.toml` when it is missing, runs the doctor checks, builds the library (through a temporary injected `SConstruct` when yours is unwired), generates and warms the fixture, launches Godot headless, and removes the fixture afterwards. Exit `0` on green, `1` on failures. Godot is auto-discovered, so no `--godot` is needed when a binary is on `PATH`, in the project tree, or in `$HOME`.

Useful variants:

```bash
./extern/gdextest/gdextest doctor                        # environment checks only
./extern/gdextest/gdextest test --keep-fixture           # keep the fixture when the run fails
./extern/gdextest/gdextest scaffold --apply              # make the SConstruct wiring permanent
```

## 5. Configure the consumer contract

`.gdextest.toml` is the single source of truth. The structured form:

```toml
[gdextest]
version = "1"
minimum_required_godot_version = "4.5"

[gdextest.tests]
sources = ["tests/**/*.cpp"]
exclude = ["tests/helpers/**"]

[gdextest.test]
timeout_ms = 30000          # per async wait
isolate_timeout_sec = 60    # whole-test async budget
flaky_retries = 3           # extra attempts for TAG_FLAKY tests

[gdextest.host]
mode = "editor"             # editor or runtime
entry_symbol = "gdextest_library_init"
plugin_class = "GdextestPlugin"

[gdextest.fixture]
directory = "build/gdextest/project"
project_name = "my extension tests"
assets = ["tests/fixtures/**"]
scan_timeout_ms = 20000

[gdextest.output]
directory = "bin"
name = "libmy_extension_tests"

[gdextest.build]
args = []                   # extra scons args, e.g. ["target=editor"]
```

Every key is documented in [Configuration](/projects/gdextest/docs/configuration). Points worth knowing:

- The `[gdextest.test]` budgets are forwarded to the runner on every CLI run. CI can raise them without rebuilding the framework.
- `scan_timeout_ms` bounds the editor's first filesystem scan in the generated fixture host.
- Source patterns are repo-root relative and must match at least one file. Vendored C dependencies compile in too; add a `**/*.c` pattern when needed.
- `host.mode = "editor"` generates the scan-safe editor-plugin fixture and runs `--headless --editor`. `host.mode = "runtime"` generates an autoload fixture and runs plain `--headless`, appropriate for runtime-only extensions.

The SConscript loads the TOML itself, so a bare `scons tests=true` and the CLI flow build the same thing.

## 6. Load your real extension

By default the code under test is whatever compiles into the test library. When a suite needs the actual extension loaded in the fixture, registered classes, editor plugins, or behavior only the real `.so` exhibits, point at it:

```toml
[gdextest.consumer_extension]
library = "addons/my_extension/bin/libmy_extension.linux.editor.x86_64.so"
```

Only one of the two files needs configuring:

- **`library` set, `manifest` omitted** — the framework walks up from the library and uses the unique `.gdextension` it finds. Covers `addons/<name>/bin/` and `addons/<name>/` layouts.
- **`manifest` set, `library` omitted** — the manifest's `[libraries]` table is read and the first entry that resolves on disk is used.

Set both keys when the search is ambiguous. When nothing is configured and the project contains exactly one `.gdextension`, `gdextest doctor` prints the exact TOML lines to add.

The fixture stages the extension under `addons/consumer/` and rewrites the manifest's `[libraries]` paths to that copy. Your real addon manifest works as-is.

## 7. Customize startup

When the extension needs services bootstrapped before the tests run, register host callbacks from your initialization code:

```cpp
#include "gdextest/host.h"

void start_test_services() { /* initialize consumer services */ }
void stop_test_services() { /* release consumer services */ }

void configure_gdextest_host() {
    gdextest::configure_host({&start_test_services, &stop_test_services});
}
```

- `bootstrap` runs on the main thread immediately before a triggered test run.
- `shutdown` runs right after the results are written.
- An empty `HostConfig` restores the no-op default.
- The callbacks are plain function pointers, so the API behaves the same on GCC, Clang, and MSVC.

Compile the file that calls `configure_gdextest_host()` into the test build. Either list it in `[gdextest.tests] sources`, or set `[gdextest.host] bootstrap = "path/to/file.cpp"` to add it explicitly. Call `configure_gdextest_host()` from your extension's normal initialization path, after Godot is initialized and before the host node is created.

## 8. Hook the framework lifecycle with adapters

For hooks beyond a single bootstrap/shutdown pair, implement an `ExtensionAdapter` and register it:

```cpp
// testsupport/adapters.cpp — any file compiled into the test build
#include "gdextest/adapter.h"
#include "my_extension/services.h"

namespace {

struct ServicesAdapter : public gdextest::ExtensionAdapter {
    void on_initialize(godot::ModuleInitializationLevel level) override {
        // Fired for each GDExtension initialization level.
        if (level == godot::MODULE_INITIALIZATION_LEVEL_SCENE) {
            my_extension::start_services();
        }
    }

    void on_uninitialize(godot::ModuleInitializationLevel level) override {
        // Fired in reverse registration order (LIFO).
        if (level == godot::MODULE_INITIALIZATION_LEVEL_SCENE) {
            my_extension::stop_services();
        }
    }

    void on_ready(godot::Node *tree_node) override {
        // Fired once, right before a triggered run starts.
    }
};

}  // namespace

GDEX_REGISTER_ADAPTER(ServicesAdapter)
```

Dispatch points:

| Callback | When it fires |
| --- | --- |
| `on_initialize` | Each initialization level, in registration order. |
| `on_uninitialize` | Each uninitialization level, in reverse order. |
| `on_ready` | Once per triggered run, with the host node, before `bootstrap`. |

Multiple adapters are supported. `GDEX_REGISTER_ADAPTER` works from any translation unit compiled into the test build. See [Architecture](/projects/gdextest/docs/architecture#the-adapter-system) for the dispatch flow.

### Replacing the reference adapter entirely

The reference adapter (`src/support/adapter.cpp`) owns trigger detection and run start. Replace it through the SConscript export when the default host lifecycle is not enough:

```python
lib = env.SConscript(
    "extern/gdextest/SConscript",
    variant_dir="build/gdextest", duplicate=0,
    exports={"env": env, "gdextest": {
        "adapter": "testsupport/adapter.cpp",   # your trigger + startup
        # "entry": "testsupport/entry.cpp",      # optional custom entry too
    }},
)
```

Your adapter must implement `void maybe_run(godot::Node*)` in namespace `gdextest_adapter`. A wrong signature fails at compile time, not at link time.

## 9. Add a custom entry point (optional)

The default entry point registers the editor plugin shell and `SignalMonitor`. Run `gdextest scaffold --apply` to generate `testsupport/entry.cpp` from a template when you need your own:

- The template uses the `plugin_class` and `entry_symbol` from your TOML. No manual copy-and-rename.
- `testsupport/` sits outside the default `tests/**/*.cpp` suite glob, so the entry compiles exactly once.
- The generated fixture wrapper instantiates exactly the class named by `[gdextest.host] plugin_class`, so keep the two in sync.

Use the godot-cpp 4.5 entry API exactly; the pre-4.5 form does not compile:

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

The generated `.gdextension` manifest in the fixture sets `entry_symbol` to the function named by `[gdextest.host] entry_symbol`.

## 10. Create a custom fixture project (optional)

The generated fixture covers every normal flow. To hand-roll one, copy `testdata/project/` from the framework repository and adapt three pieces.

**`project.godot`** — register the extension and enable the plugin:

```ini
[native_extensions]
paths=["res://mytest.gdextension"]

[editor_plugins]
enabled=PackedStringArray("res://addons/gdextest/plugin.cfg")
```

**`mytest.gdextension`** — point at your test library. One `linux.debug.x86_64` entry is enough; editor builds carry the `debug` feature tag, so it matches `--headless --editor` runs too:

```ini
[configuration]
entry_symbol = "my_library_init"
compatibility_minimum = "4.5"

[libraries]
linux.debug.x86_64 = "res://bin/libmytest-test.linux.template_debug.x86_64.so"
```

**`addons/gdextest/plugin.cfg` + `plugin.gd`** — the script must extend `EditorPlugin` directly (extending your native plugin class is rejected by the plugin manager). It instantiates the native plugin once the editor filesystem scan has finished:

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
```

The scan wait is mandatory: quitting during the first scan races the scan thread and can crash the editor. The native plugin owns the run and requests process shutdown itself; do not free it during editor teardown.

## 11. Run in CI

### Single job

```yaml
- name: Install SCons
  run: python3 -m pip install scons
- name: Download Godot 4.5
  run: |
    curl -fsSL -o godot.zip https://github.com/godotengine/godot/releases/download/4.5-stable/Godot_v4.5-stable_linux.x86_64.zip
    unzip -o godot.zip
    chmod +x Godot_v4.5-stable_linux.x86_64
- name: Run gdextest
  run: ./extern/gdextest/gdextest test --godot "$GITHUB_WORKSPACE/Godot_v4.5-stable_linux.x86_64" --json=results.json --junit=results.xml
```

The exit code gates the job. The JUnit file surfaces failures and skips as inline annotations.

`gdextest init --ci` writes this workflow for you.

### Parallel jobs

One job per shard, then a merge job:

```yaml
- name: Run shard 0/4
  run: ./extern/gdextest/gdextest test --godot "$GODOT" --shard=0/4 --json=shard0.json
# ... shards 1-3 ...
- name: Merge shard results
  run: ./extern/gdextest/gdextest report 'shard*.json' --json=merged.json --junit=merged.xml
```

`report` exits `1` when any merged test failed, so the merge job gates the pipeline.

### Hermeticity

The CLI keeps `user://` hermetic: it wipes `build/gdextest/user-data` before every run and points `XDG_DATA_HOME` there. No extra CI setup is needed.

## Where to go from here

- [Configuration](/projects/gdextest/docs/configuration) — every key and default.
- [CLI reference](/projects/gdextest/docs/cli) — every command, flag, and output format.
- [Troubleshooting](/projects/gdextest/docs/troubleshooting) — when something goes red.
- [Architecture](/projects/gdextest/docs/architecture) — how the framework works inside.
