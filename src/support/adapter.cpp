// Per-extension adapter (plan §2, §16). This is the ONLY file that knows the
// extension's shape and wiring. M0-verified (see docs/testing/notes.md):
//  - trigger detection checks env + BOTH cmdline lists (before/after "--")
//  - editor mode hooks from EditorPlugin::_ready() (autoload under --editor hangs)
//  - exit via SceneTree::quit(code); OS::set_exit_code is not bound in 4.5
//
// Compiled into the test build only (GDX_TESTS_ENABLED). ~40 lines by design.
#ifdef GDX_TESTS_ENABLED

#include <godot_cpp/classes/editor_plugin.hpp>
#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/classes/scene_tree.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>

namespace gdextest { void run_all_and_quit(void *tree_node); }

// Optional consumer hook. A host can provide tests/gdxtest_bootstrap.cpp with
// this symbol; the generic adapter remains linkable when it is absent.
#if defined(__GNUC__) || defined(__clang__)
extern "C" void gdxtest_consumer_bootstrap() __attribute__((weak));
#else
extern "C" void gdxtest_consumer_bootstrap();
#endif

namespace {

// M0-verified trigger predicate: env var OR --gdxtest-run in either cmdline list.
bool test_trigger_present() {
    using namespace godot;
    OS *os = OS::get_singleton();
    if (!os) return false;
    if (os->has_environment("GDX_RUN_TESTS")) return true;
    PackedStringArray eng = os->get_cmdline_args();        // before "--"
    PackedStringArray usr = os->get_cmdline_user_args();  // after "--"
    return eng.has("--gdxtest-run") || usr.has("--gdxtest-run");
}

// Bootstrap callback (plan §2): start only the services the code under test needs.
// For this repo there are none yet; real hosts list theirs here.
void bootstrap() {
#if defined(__GNUC__) || defined(__clang__)
    if (gdxtest_consumer_bootstrap) gdxtest_consumer_bootstrap();
#endif
}

} // namespace

namespace gdx_adapter {

// Called from EditorPlugin::_ready() (editor mode) or an autoload _ready() (runtime).
// No-op unless triggered; hands the live tree node to the framework runner.
void maybe_run(godot::Node *tree_node) {
    if (!test_trigger_present()) return;
    bootstrap();
    gdextest::run_all_and_quit(tree_node);
}

} // namespace gdx_adapter

#endif // GDX_TESTS_ENABLED
