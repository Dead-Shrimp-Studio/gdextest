#include "gdextest/registry.h"

#include <algorithm>
#include <cstring>

namespace gdextest {

TestRegistry &TestRegistry::instance() {
    // Function-local static — safe under the "no Godot types in static init" rule.
    static TestRegistry reg;
    return reg;
}

void TestRegistry::add(TestCase tc) { cases_.push_back(tc); }
const std::vector<TestCase> &TestRegistry::all() const { return cases_; }

namespace {

// Simple glob: '*' matches any run of chars, '?' matches one, '.' is literal.
bool glob_match(const char *pat, const char *str) {
    while (*pat) {
        if (*pat == '*') {
            // Collapse runs of '*'.
            while (*pat == '*') ++pat;
            if (!*pat) return true;
            for (; *str; ++str) {
                if (glob_match(pat, str)) return true;
            }
            return glob_match(pat, str);
        } else if (*pat == '?') {
            if (!*str) return false;
            ++pat; ++str;
        } else {
            if (*pat != *str) return false;
            ++pat; ++str;
        }
    }
    return *str == '\0';
}

bool name_matches(const TestCase &tc, const Filter &f) {
    // Build "suite.name" for matching; also allow bare suite or name globs.
    std::string full = std::string(tc.suite) + "." + std::string(tc.name);
    const char *cstr = full.c_str();

    // Split patterns into positives and negatives.
    bool any_positive = false;
    bool positive_hit = false;
    for (const std::string &p : f.patterns) {
        if (!p.empty() && p[0] == '-') continue;  // negative handled below
        any_positive = true;
        // Try the full form, the suite, and the name.
        if (glob_match(p.c_str(), cstr) ||
            glob_match(p.c_str(), tc.suite) ||
            glob_match(p.c_str(), tc.name)) {
            positive_hit = true;
        }
    }
    if (any_positive && !positive_hit) return false;

    // Negatives exclude on any match.
    for (const std::string &p : f.patterns) {
        if (p.empty() || p[0] != '-') continue;
        const char *neg = p.c_str() + 1;
        if (glob_match(neg, cstr) ||
            glob_match(neg, tc.suite) ||
            glob_match(neg, tc.name)) {
            return false;
        }
    }
    return true;
}

bool tags_ok(const TestCase &tc, const Filter &f) {
    if (f.include_tags && (tc.tags & f.include_tags) == 0) return false;
    if (f.exclude_tags && (tc.tags & f.exclude_tags) != 0) return false;
    return true;
}

// Stable hash for sharding (so the same test lands in the same shard across runs).
uint32_t hash_str(const char *s) {
    uint32_t h = 2166136261u;
    for (; *s; ++s) { h ^= static_cast<uint8_t>(*s); h *= 16777619u; }
    return h;
}

} // namespace

std::vector<const TestCase *> TestRegistry::select(const Filter &f) const {
    std::vector<const TestCase *> out;
    for (const TestCase &tc : cases_) {
        if (!name_matches(tc, f)) continue;
        if (!tags_ok(tc, f)) continue;
        if (f.shard_count > 1) {
            uint32_t h = hash_str(tc.suite) ^ (hash_str(tc.name) * 2654435761u);
            if ((h % static_cast<uint32_t>(f.shard_count)) !=
                static_cast<uint32_t>(f.shard_index)) {
                continue;
            }
        }
        out.push_back(&tc);
    }

    if (f.shuffle) {

        unsigned s = f.shuffle_seed ? f.shuffle_seed : 1;
        for (size_t i = out.size(); i > 1; --i) {
            s = s * 1103515245u + 12345u;
            size_t j = (s / 65536u) % i;
            std::swap(out[i - 1], out[j]);
        }
    }

    return out;
}

} // namespace gdextest
