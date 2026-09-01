// Per-extension adapter for the generated gdextest host.
#ifdef GDEXTEST_ENABLED

#include "gdextest/adapter.h"

#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>

namespace gdextest {
void bootstrap_host();
void run_all_and_quit(void *tree_node);
}

namespace {

bool test_trigger_present() {
    godot::OS *os = godot::OS::get_singleton();
    if (!os) return false;
    if (os->has_environment("GDX_RUN_TESTS")) return true;
    return os->get_cmdline_args().has("--gdextest-run") ||
           os->get_cmdline_user_args().has("--gdextest-run");
}

} // namespace

namespace gdextest_adapter {

void maybe_run(godot::Node *tree_node) {
    if (!test_trigger_present()) return;
    if (auto *adapter = gdextest::AdapterRegistry::instance().get_adapter()) {
        adapter->on_ready(tree_node);
    }
    gdextest::bootstrap_host();
    gdextest::run_all_and_quit(tree_node);
}

} // namespace gdextest_adapter

#endif // GDEXTEST_ENABLED