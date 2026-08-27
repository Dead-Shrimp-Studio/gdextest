// Consumer hooks for extension-specific test setup and teardown.
#pragma once

#if defined(_WIN32)
#define GDEXTEST_HOST_API __declspec(dllexport)
#elif defined(gdextest_BUILDING)
#define GDEXTEST_HOST_API __attribute__((visibility("default")))
#else
#define GDEXTEST_HOST_API
#endif

namespace gdextest {

struct HostConfig {
    void (*bootstrap)() = nullptr;
    void (*shutdown)() = nullptr;
};

GDEXTEST_HOST_API void configure_host(const HostConfig &config);
GDEXTEST_HOST_API void bootstrap_host();
GDEXTEST_HOST_API void shutdown_host();

} // namespace gdextest
