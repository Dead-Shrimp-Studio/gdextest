
#pragma once

#include <cstdint>

namespace gdextest {

// Tag bitmask carried by each TestCase.
enum Tag : uint32_t {
    TAG_UNIT = 1 << 0,
    TAG_INTEGRATION = 1 << 1,
    TAG_ASYNC = 1 << 2,
    TAG_SLOW = 1 << 3,
    TAG_FLAKY = 1 << 4,
};

// Defaults (overridable here if a host wants different budgets). The runner
// overrides these at runtime from the CLI (--gdextest-timeout-ms,
// --gdextest-isolate-timeout-sec, --gdextest-flaky-retries), which the CLI
// populates from the consumer's .gdextest.toml ([gdextest.test]).
inline constexpr int kDefaultTimeoutMs = 30000;        // per async wait
inline constexpr int kDefaultFlakyRetries = 3;
inline constexpr int kDefaultIsolateTimeoutSec = 60;

// Runtime-tunable budgets. Function-local statics in an inline accessor give a
// single per-program instance (plain C++, no Godot types).
struct RuntimeConfig {
    int timeout_ms = kDefaultTimeoutMs;
    int isolate_timeout_sec = kDefaultIsolateTimeoutSec;
    int flaky_retries = kDefaultFlakyRetries;
};
inline RuntimeConfig &runtime_config() {
    static RuntimeConfig config;
    return config;
}

} // namespace gdextest
