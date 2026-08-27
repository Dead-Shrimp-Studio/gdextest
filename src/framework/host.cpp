#include "gdextest/host.h"

namespace gdextest {
namespace {
HostConfig g_host_config;
}

void configure_host(const HostConfig &config) {
    g_host_config = config;
}

void bootstrap_host() {
    if (g_host_config.bootstrap) {
        g_host_config.bootstrap();
    }
}

void shutdown_host() {
    if (g_host_config.shutdown) {
        g_host_config.shutdown();
    }
}

} // namespace gdextest
