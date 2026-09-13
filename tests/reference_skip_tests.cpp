
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