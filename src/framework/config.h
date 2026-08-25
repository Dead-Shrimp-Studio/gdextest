// Single customization point for the gdextest framework.
// Hosts with a naming clash redefine these here (and only here) — see plan §15.
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

// Defaults (overridable here if a host wants different budgets).
inline constexpr int kDefaultTimeoutMs = 30000;   // per async wait
inline constexpr int kDefaultFlakyRetries = 3;
inline constexpr int kDefaultIsolateTimeoutSec = 60;

} // namespace gdextest
