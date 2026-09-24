
#ifdef GDEXTEST_ENABLED

#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/classes/window.hpp>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/utility_functions.hpp>
#include <godot_cpp/core/memory.hpp> // memnew / memdelete

#include "gdextest/assert.h"
#include "gdextest/engine.h"
#include "gdextest/registry.h"
#include "gdextest/signals.h"

// The engine host (SceneTree) is live and reachable from the context.
GDEX_TEST_T(engine, tree_is_live_and_reachable, TAG_INTEGRATION) {
    godot::SceneTree *tree = gdextest::engine_tree(ctx);
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(tree));
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(tree->get_root()));
}

// Engine singletons are available to test bodies (not just to the adapter).
GDEX_TEST_T(engine, singleton_is_live, TAG_INTEGRATION) {
    godot::OS *os = godot::OS::get_singleton();
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(os));
    GDEX_EXPECT_GT(os->get_processor_count(), 0);
}

// A body can build real scene-tree structure: create, parent, and free a node.
GDEX_TEST_T(engine, can_create_and_destroy_node, TAG_INTEGRATION) {
    godot::SceneTree *tree = gdextest::engine_tree(ctx);
    if (!tree) {
        GDEX_FAIL("no live scene tree");
        return;
    }
    godot::Window *root = tree->get_root();
    GDEX_EXPECT_NOT_NULL(static_cast<void *>(root));

    godot::Node *child = memnew(godot::Node);
    ctx.track_object(child);
    child->set_name("gdextest-temp");
    root->add_child(child);
    GDEX_EXPECT(child->get_parent() == static_cast<godot::Node *>(root));
    GDEX_EXPECT(child->get_name() == godot::StringName("gdextest-temp"));

    root->remove_child(child);
    memdelete(child);
}

// Tracking a freed object is safe: teardown resolves its instance ID and does
// not dereference the stale pointer.
GDEX_TEST_T(engine, tracked_object_is_clean_after_free, TAG_INTEGRATION) {
    godot::Node *child = memnew(godot::Node);
    ctx.track_object(child);
    const uint64_t id = child->get_instance_id();
    memdelete(child);
    GDEX_EXPECT_NULL(godot::UtilityFunctions::instance_from_id(static_cast<int64_t>(id)));
}

// A RefCounted kept alive by the test is detected at teardown through its
// instance ID and reference count. This test deliberately releases its local
// reference before teardown, so it remains green.
GDEX_TEST_T(engine, tracked_ref_is_released_cleanly, TAG_INTEGRATION) {
    godot::Ref<godot::RefCounted> value = memnew(godot::RefCounted);
    ctx.track_ref(value.ptr());
    value.unref();
    GDEX_EXPECT_TRUE(true);
}

GDEX_TEST_T(engine, signal_monitor_instantiation, TAG_INTEGRATION) {
    gdextest::SignalMonitor &monitor = ctx.signals();
    const uint64_t id = monitor.get_instance_id();
    GDEX_EXPECT_NOT_NULL(godot::UtilityFunctions::instance_from_id(static_cast<int64_t>(id)));
}

GDEX_TEST_T(engine, signal_monitor_base_case, TAG_INTEGRATION) {
    gdextest::SignalMonitor &monitor = ctx.signals();
    GDEX_EXPECT_TRUE(monitor.evaluate());
}

GDEX_TEST_T(engine, signal_monitor_emission, TAG_INTEGRATION) {
    gdextest::SignalMonitor &monitor = ctx.signals();
    godot::SceneTree *tree = gdextest::engine_tree(ctx);

    monitor.add(tree, "node_added", 1);
    GDEX_EXPECT_FALSE(monitor.evaluate());

    monitor.remove(tree, "node_added");
    GDEX_EXPECT_EQ(monitor.get_emission_count(tree, "node_added"), 0);
}

#endif // GDEXTEST_ENABLED