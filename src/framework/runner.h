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

} // namespace gdextest
