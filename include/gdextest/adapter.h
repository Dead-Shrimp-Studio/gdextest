#pragma once

#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <vector>

namespace gdextest {

class ExtensionAdapter {
public:
    virtual ~ExtensionAdapter() = default;

    virtual void on_initialize(godot::ModuleInitializationLevel level) {}
    virtual void on_uninitialize(godot::ModuleInitializationLevel level) {}
    virtual void on_ready(godot::Node *tree_node) {}
};

class AdapterRegistry {
public:
    static AdapterRegistry &instance() {
        static AdapterRegistry registry;
        return registry;
    }

    void add_adapter(ExtensionAdapter *adapter) {
        if (adapter) {
            adapters_.push_back(adapter);
        }
    }

    const std::vector<ExtensionAdapter *> &adapters() const {
        return adapters_;
    }

    void dispatch_initialize(godot::ModuleInitializationLevel level) {
        for (auto *adapter : adapters_) {
            adapter->on_initialize(level);
        }
    }

    void dispatch_uninitialize(godot::ModuleInitializationLevel level) {
        // Reverse order (LIFO) for clean teardown
        for (auto it = adapters_.rbegin(); it != adapters_.rend(); ++it) {
            (*it)->on_uninitialize(level);
        }
    }

    void dispatch_ready(godot::Node *tree_node) {
        for (auto *adapter : adapters_) {
            adapter->on_ready(tree_node);
        }
    }

private:
    AdapterRegistry() = default;
    std::vector<ExtensionAdapter *> adapters_;
};

template <typename T>
struct AdapterRegistrar {
    AdapterRegistrar() {
        static T instance;
        AdapterRegistry::instance().add_adapter(&instance);
    }
};

} // namespace gdextest

#define GDEX_REGISTER_ADAPTER(AdapterClass) \
    static const ::gdextest::AdapterRegistrar<AdapterClass> gdx_adapter_##AdapterClass##_instance;

namespace gdextest_adapter {
void maybe_run(godot::Node *tree_node);
}