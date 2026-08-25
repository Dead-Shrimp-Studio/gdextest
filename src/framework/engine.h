// Engine access for integration tests (engine boundary, like runner.h).
//
// Pure C++ test bodies (default GDX_TEST) never include this. Suites that want the
// live engine include it and opt into engine access via the opaque handle stored on
// their TestContext by the runner. It is the ONLY place besides runner.cpp / the
// adapter that touches godot-cpp types.
#pragma once

#include "context.h"

#include <godot_cpp/classes/node.hpp>
#include <godot_cpp/classes/scene_tree.hpp>
#include <godot_cpp/classes/window.hpp>   // SceneTree::get_root() returns Window*

namespace gdextest {

// The live engine host node handed to run_all_and_quit — the adapter's plugin node
// in this repo. Null when no engine is attached (e.g. a pure self-test).
inline godot::Node *engine_node(TestContext &ctx) {
    return static_cast<godot::Node *>(ctx.engine_handle());
}

// The live SceneTree, or null if there is no engine node or it has no tree yet.
inline godot::SceneTree *engine_tree(TestContext &ctx) {
    godot::Node *n = engine_node(ctx);
    return n ? n->get_tree() : nullptr;
}

} // namespace gdextest