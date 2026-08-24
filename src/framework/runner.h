// Runner: the engine boundary. Parses --gdxtest-* flags, runs selected tests
// synchronously (M1; async lands at M2), writes JSON + human output, and exits via
// SceneTree::quit(code). This is the only framework header that pulls in godot-cpp.
//
// Plan §3 (execution model), §5.5 (reporting), §15 (boundary convention).
#pragma once

#include "context.h"

namespace gdextest {

// Entry point called by the host adapter (plan §3 "Triggered entry point").
// `tree_node` is any Node whose get_tree() yields the live SceneTree — typically the
// EditorPlugin (editor mode) or the autoload Node (runtime mode).
//
// No-op unless a trigger is present (GDX_RUN_TESTS env, or --gdxtest-run in either
// cmdline arg list), so a host may call it unconditionally from _ready().
//
// Exit codes (plan §3): 0 = all passed, 1 = ≥1 failure, 2 = usage error.
void run_all_and_quit(void *tree_node);

// Run a single test body in isolation with a fresh TestContext and return its
// failure count. Exposed for the self-test suite (plan §12 "self": verify macros
// record failures). Bodies use the same GDX_EXPECT_* macros; `ctx` is injected.
int run_sub_and_count_failures(void (*body)(TestContext &));

} // namespace gdextest
