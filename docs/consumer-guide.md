# Consumer guide

How another GDExtension repo integrates gdextest. This repo is itself the reference
consumer — every step below is what `src/`, `tests/`, `testdata/project/`, and
`run_tests.sh` do here, so treat them as the working example.

## Model

There is no separate runner binary. The framework is compiled **into your test build**: a
test-only shared object containing the framework core, an entry point, your per-extension
adapter, and your suites. A fixture Godot project loads that `.so`; a headless run executes
the suites and exits with pass/fail. Release builds are untouched.

```
your repo/
  extern/gdextest/          # this framework (git submodule)
  src/…                     # your extension sources (untouched by the framework)
  tests/                    # your GDX_TEST suites
  testsupport/
    adapter.cpp             # your adapter (bootstrap + hook)
    entry.cpp               # GDExtension entry (register your plugin)
  testdata/project/         # fixture project (see below)
  SConstruct                # add the test target (see Build)
```

## 1. Pull in the framework

```bash
git submodule add <this-repo-url> extern/gdextest
git submodule update --init --recursive   # also pulls extern/gdextest/extern/godot-cpp
```

Your build already vendors godot-cpp (every GDExtension does); the framework expects to
compile against a 4.5 binding set — it uses `EditorPlugin`, `SceneTree::quit`,
`OS::get_cmdline_args/get_cmdline_user_args`, and the 4.5 `GDExtensionBinding::InitObject`
API.

## 2. Write suites

Plain C++ files using the macros — see [api-reference.md](api-reference.md) for the full
surface:

```cpp
#include "framework/assert.h"
#include "framework/registry.h"
#include "my_extension/math_utils.h"   // your code under test

GDX_TEST(math_utils, clamp_keeps_value_in_range) {
    GDX_EXPECT_EQ(clamp(5, 0, 10), 5);
    GDX_EXPECT_EQ(clamp(-1, 0, 10), 0);
    GDX_EXPECT_EQ(clamp(42, 0, 10), 10);
}
```

Engine-facing tests run inside a real Godot process, so singletons and your registered
classes are live — even though a test body only receives a `TestContext&` (the runner does
not expose the `SceneTree` to bodies yet):

```cpp
GDX_TEST_T(my_extension, class_is_registered, TAG_INTEGRATION) {
    GDX_EXPECT_TRUE(godot::ClassDB::class_exists("MyCustomNode"));
    GDX_EXPECT_NE(godot::OS::get_singleton()->get_processor_count(), 0);
}
```

## 3. Write the adapter

`adapter.cpp` is the **only file that knows your extension's wiring**. Model it on
[`src/support/adapter.cpp`](../src/support/adapter.cpp) — ~40 lines by design:

```cpp
#ifdef GDX_TESTS_ENABLED   // test build only

#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/classes/scene_tree.hpp>

namespace gdextest { void run_all_and_quit(void *tree_node); }

namespace {
bool test_trigger_present() {
    godot::OS *os = godot::OS::get_singleton();
    if (!os) return false;
    if (os->has_environment("GDX_RUN_TESTS")) return true;
    // Check BOTH lists — args before "--" and after "--" (notes.md §3.2).
    return os->get_cmdline_args().has("--gdxtest-run") ||
           os->get_cmdline_user_args().has("--gdxtest-run");
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

#endif // GDX_TESTS_ENABLED
```

## 4. Add the entry point

Copy [`src/gdx_test_entry.cpp`](../src/gdx_test_entry.cpp) and rename the plugin class to
match your extension. It registers an `EditorPlugin` whose `_ready()` calls your adapter.
Use the godot-cpp 4.5 entry API exactly (the pre-4.5 form does not compile):

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

## 5. Create the fixture project

Copy [`testdata/project/`](../testdata/project/) and adapt. Three pieces:

**`project.godot`** — registers the extension and enables the plugin:

```ini
[native_extensions]
paths=["res://mytest.gdextension"]

[editor_plugins]
enabled=PackedStringArray("res://addons/gdxtest/plugin.cfg")
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

**`addons/gdxtest/plugin.cfg` + `plugin.gd`** — the plugin script must `extend
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

## 6. Build

Call the framework's reusable [`SConscript`](../SConscript) **after** your godot-cpp
`SConscript` (the env must already carry godot-cpp's include paths and `LIBS`). It compiles
 the framework core, your entry, your adapter, and your suites into a separately-named
shared object with `GDX_TESTS_ENABLED` defined, and handles all the fiddly bits: framework
include paths, `-fexceptions` (godot-cpp defaults to `-fno-exceptions`), the `.so` suffix,
and an env `Clone` so your real extension build stays untouched:

```python
# your SConstruct, after wiring godot-cpp into `env`:
lib = env.SConscript(
    "extern/gdextest/SConscript",
    variant_dir="build/gdextest", duplicate=0,   # keep objects out of the submodule
    exports={"env": env, "gdxtest": {
        "enabled":  env.get("tests", False),    # or omit -> `scons tests=true`
        "entry":    "testsupport/entry.cpp",    # required
        "adapter":  "testsupport/adapter.cpp",  # required
        "suites":   Glob("tests/*.cpp"),
        "out_dir":  "bin",
        "out_name": "libgdextest",
    }},
)
if lib:
    Default(lib)
```

This produces `bin/libgdextest.linux.template_debug.x86_64.so` (the platform suffix comes
from `env["suffix"]`, which godot-cpp sets). Paths in `gdxtest` resolve against your
project root. Optional extras your env can carry: `sanitize=true` (ASan/UBSan) and
`coverage=true` flags are applied to `env` before the call and inherited by the test target
(this repo's `SConstruct` is the working example).

## 7. Run and wire into CI

```bash
godot --headless --editor --path testdata/project -- \
    --gdxtest-run --gdxtest-json=results.json
```

Exit code `0` = green, `1` = red — map it straight to your pipeline. For parallel CI use
`--gdxtest-shard=k/n` (stable assignment, disjoint shards). Set `XDG_DATA_HOME` to a temp
dir in CI so `user://` writes are hermetic (`testing/notes.md` §3.1). See
[cli.md](cli.md) for the full flag reference.

## Troubleshooting

- **Editor hangs on `--headless --editor`:** the run isn't triggering — no `--gdxtest-run`
  / `GDX_RUN_TESTS`, or your adapter isn't being called. Check the plugin is enabled in
  `project.godot` and the `.gdextension` entry symbol matches your `init` function.
- **Editor crashes on shutdown:** the run happened before the filesystem scan finished —
  keep the `is_scanning()` deferral in `plugin.gd`.
- **`Script inherits from native type … can't be assigned to EditorPlugin`:** the plugin
  script must extend `EditorPlugin` directly, not your native plugin class.
- **Link errors with `-fno-exceptions`:** add `-fexceptions` to the test target's
  `CXXFLAGS`.
