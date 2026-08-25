// Minimal GDExtension entry + EditorPlugin shell (test build only).
// The plugin's _ready() is the M0-verified safe editor hook (plan §3).
#ifdef GDEXTEST_ENABLED

#include <godot_cpp/classes/editor_plugin.hpp>
#include <godot_cpp/godot.hpp>

namespace gdextest_adapter { void maybe_run(godot::Node *tree_node); }

// The EditorPlugin the fixture project enables. Its _ready() is the safe hook point
// (autoload under --editor hangs — see docs/testing/notes.md §3.3).
class GdextestPlugin : public godot::EditorPlugin {
    GDCLASS(GdextestPlugin, godot::EditorPlugin)

protected:
    static void _bind_methods() {}

public:
    void _ready() override {
        godot::Node *self = this;
        gdextest_adapter::maybe_run(self);
    }
};

// --- GDExtension module lifecycle -------------------------------------------
using namespace godot;

void initialize_test_module(ModuleInitializationLevel p_level) {
    if (p_level != MODULE_INITIALIZATION_LEVEL_EDITOR) return;
    ClassDB::register_class<GdextestPlugin>();
}

void uninitialize_test_module(ModuleInitializationLevel p_level) {
    if (p_level != MODULE_INITIALIZATION_LEVEL_EDITOR) return;
}

extern "C" {

GDExtensionBool GDE_EXPORT gdextest_library_init(
        GDExtensionInterfaceGetProcAddress p_get_proc_address,
        const GDExtensionClassLibraryPtr p_library,
        GDExtensionInitialization *r_initialization) {
    godot::GDExtensionBinding::InitObject init_obj(p_get_proc_address, p_library,
                                                   r_initialization);
    init_obj.register_initializer(&initialize_test_module);
    init_obj.register_terminator(&uninitialize_test_module);
    // Fire our initializer at (and after) the EDITOR level only; the guard inside
    // initialize_test_module registers the plugin exactly once, at that level.
    init_obj.set_minimum_library_initialization_level(godot::MODULE_INITIALIZATION_LEVEL_EDITOR);
    return init_obj.init();
}

}  // extern "C"

#endif // GDEXTEST_ENABLED
