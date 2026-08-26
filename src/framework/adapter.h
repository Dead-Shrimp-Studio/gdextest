// Adapter contract (docs §4.1): the interface between the generic test entry
// point and the one file that knows your extension's wiring.
//
// The default entry (src/gdextest_entry.cpp) registers an EditorPlugin whose
// _ready() defers here; the runtime fixture autoload does the same. Custom
// adapters include this header and define `maybe_run`, so a signature mismatch
// fails at compile time instead of link time with a cryptic undefined symbol.
#pragma once

#include <godot_cpp/classes/node.hpp>

namespace gdextest_adapter {

// Called exactly once the engine is ready, with the host node the run was
// triggered from. Implementations check the trigger (--gdextest-run or
// GDX_RUN_TESTS) and, when present, own the test run: bootstrap consumer
// services, call gdextest::run_all_and_quit(node), and let the runner exit.
void maybe_run(godot::Node *tree_node);

} // namespace gdextest_adapter
