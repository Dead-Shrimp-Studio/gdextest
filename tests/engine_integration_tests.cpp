// Engine integration suite (plan roadmap: expose live SceneTree to test bodies).
//
// These tests exercise the LIVE Godot engine, so they are the first real
// consumers of the opaque engine handle stored on TestContext (see
// framework/engine.h). They run only when the suite is invoked through the
// engine trigger (the fixture's EditorPlugin), where the runner attaches the
// live tree node to each test's context.
#ifdef GDX_TESTS_ENABLED

#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/classes/os.hpp>
#include <godot_cpp/classes/window.hpp>
#include <godot_cpp/core/memory.hpp> // memnew / memdelete

#include "framework/assert.h"
#include "framework/engine.h"
#include "framework/registry.h"

// The engine host (SceneTree) is live and reachable from the context.
GDX_TEST_T(engine, tree_is_live_and_reachable, TAG_INTEGRATION) {
    godot::SceneTree *tree = gdextest::engine_tree(ctx);
    GDX_EXPECT_NOT_NULL(static_cast<void *>(tree));
    GDX_EXPECT_NOT_NULL(static_cast<void *>(tree->get_root()));
}

// Engine singletons are available to test bodies (not just to the adapter).
GDX_TEST_T(engine, singleton_is_live, TAG_INTEGRATION) {
    godot::OS *os = godot::OS::get_singleton();
    GDX_EXPECT_NOT_NULL(static_cast<void *>(os));
    GDX_EXPECT_GT(os->get_processor_count(), 0);
}

// A body can build real scene-tree structure: create, parent, and free a node.
GDX_TEST_T(engine, can_create_and_destroy_node, TAG_INTEGRATION) {
    godot::SceneTree *tree = gdextest::engine_tree(ctx);
    if (!tree) {
        GDX_FAIL("no live scene tree");
        return;
    }
    godot::Window *root = tree->get_root();
    GDX_EXPECT_NOT_NULL(static_cast<void *>(root));

    godot::Node *child = memnew(godot::Node);
    child->set_name("gdxtest-temp");
    root->add_child(child);
    GDX_EXPECT(child->get_parent() == static_cast<godot::Node *>(root));
    GDX_EXPECT(child->get_name() == godot::StringName("gdxtest-temp"));

    root->remove_child(child);
    memdelete(child);
}

#endif // GDX_TESTS_ENABLED