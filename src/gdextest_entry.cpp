// Minimal GDExtension entry + EditorPlugin shell (test build only).
#ifdef GDEXTEST_ENABLED

#include "gdextest/adapter.h"
#include "gdextest/signals.h"

#include <godot_cpp/classes/editor_plugin.hpp>
#include <godot_cpp/godot.hpp>

class GdextestPlugin : public godot::EditorPlugin {
    GDCLASS(GdextestPlugin, godot::EditorPlugin)

protected:
    static void _bind_methods() {
        godot::ClassDB::bind_method(godot::D_METHOD("_run_tests"), &GdextestPlugin::_run_tests);
    }

public:
    void _ready() override {
        call_deferred("_run_tests");
    }

    void _run_tests() {
        gdextest_adapter::maybe_run(this);
    }
};

// --- GDExtension module lifecycle -------------------------------------------
using namespace godot;

void initialize_test_module(ModuleInitializationLevel p_level) {
    if (auto *adapter = gdextest::AdapterRegistry::instance().get_adapter()) {
        adapter->on_initialize(p_level);
    }

    if (p_level == MODULE_INITIALIZATION_LEVEL_EDITOR) {
        GDREGISTER_CLASS(gdextest::SignalMonitor);
        ClassDB::register_class<GdextestPlugin>();
    }
}

void uninitialize_test_module(ModuleInitializationLevel p_level) {
    if (auto *adapter = gdextest::AdapterRegistry::instance().get_adapter()) {
        adapter->on_uninitialize(p_level);
    }
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
    init_obj.set_minimum_library_initialization_level(godot::MODULE_INITIALIZATION_LEVEL_CORE);
    return init_obj.init();
}

}  // extern "C"

#endif // GDEXTEST_ENABLED