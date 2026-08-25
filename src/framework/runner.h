// Runner: the Godot-facing test execution boundary.
#pragma once

#include "context.h"
#include "host.h"

#if defined(_WIN32)
#define GDEXTEST_API __declspec(dllexport)
#elif defined(gdextest_BUILDING)
#define GDEXTEST_API __attribute__((visibility("default")))
#else
#define GDEXTEST_API
#endif

namespace gdextest {

GDEXTEST_API void run_all_and_quit(void *tree_node);
GDEXTEST_API int run_sub_and_count_failures(void (*body)(TestContext &));

// Run a single test body with a fresh TestContext and write its result as a
// single-entry JSON document to `path` (same schema as --gdextest-json).
// Returns the body's failure count. Used by the self-test suite to verify the
// JSON writer without a full engine run.
GDEXTEST_API int run_sub_and_write_json(void (*body)(TestContext &), const char *path);

} // namespace gdextest
