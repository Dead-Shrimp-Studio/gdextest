// Reference suite: runtime test skipping (roadmap: skip support).
//
// GDEX_SKIP(reason) marks the current test as skipped for a runtime reason and stops
// the body. A skipped test counts in the `skip` totals, never as a pass or failure,
// so CI that treats a skip as "not run" sees it via the JSON `skip` count / a
// per-test status of "skipped".
//
// This test demonstrates the precondition pattern: the body only has meaning when
// an optional service is present. Here the stand-in is an environment variable; a
// real host would instead check whether a service/singleton/fixture is available.
#if defined(GDEXTEST_ENABLED)

#include <cstdlib>

#include "gdextest/assert.h"
#include "gdextest/registry.h"

GDEX_TEST(skip_demo, requires_optional_benchmark_service) {
    if (std::getenv("GDX_BENCHMARK_SERVICE") == nullptr) {
        GDEX_SKIP("precondition not met: GDX_BENCHMARK_SERVICE is unset");
    }
    // Unreachable in the default run — exercising the assertion below would only
    // happen when the optional service is present.
    GDEX_EXPECT_TRUE(true);
}

#endif // GDEXTEST_ENABLED