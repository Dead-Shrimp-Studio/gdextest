#pragma once

#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/core/class_db.hpp>

namespace gdextest {

class ExtensionAdapter {
public:
    virtual ~ExtensionAdapter() = default;

    // Called on every module init level: CORE, SERVERS, SCENE, EDITOR
    virtual void on_initialize(godot::ModuleInitializationLevel level) {}
    virtual void on_uninitialize(godot::ModuleInitializationLevel level) {}

    // Called once the test runner node is in the SceneTree
    virtual void on_ready(godot::Node *tree_node) {}
};

class AdapterRegistry {
public:
    static AdapterRegistry &instance() {
        static AdapterRegistry registry;
        return registry;
    }

    void set_adapter(ExtensionAdapter *adapter) { adapter_ = adapter; }
    ExtensionAdapter *get_adapter() const { return adapter_; }

private:
    AdapterRegistry() = default;
    ExtensionAdapter *adapter_ = nullptr;
};

template <typename T>
struct AdapterRegistrar {
    AdapterRegistrar() {
        static T instance;
        AdapterRegistry::instance().set_adapter(&instance);
    }
};

} // namespace gdextest

#define GDEX_REGISTER_ADAPTER(AdapterClass) \
    static const ::gdextest::AdapterRegistrar<AdapterClass> gdx_adapter_registrar_instance;

namespace gdextest_adapter {
void maybe_run(godot::Node *tree_node);
} // namespace gdextest_adapter