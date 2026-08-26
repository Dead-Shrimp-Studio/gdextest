// Host suite #1 (plan §14 M1: "pure"). Exercises pure logic — the §12 "unit" category.
// Until the real extension has modules to test, this stands in with a tiny utility the
// host is expected to provide (or a std-only equivalent). Compiled under GDEXTEST_ENABLED.
#ifdef GDEXTEST_ENABLED

#include <string>

#include "framework/assert.h"
#include "framework/registry.h"

namespace {  // a trivial pure function the suite exercises
std::string trim(const std::string &s) {
    size_t b = 0, e = s.size();
    while (b < e && (s[b] == ' ' || s[b] == '\t')) ++b;
    while (e > b && (s[e - 1] == ' ' || s[e - 1] == '\t')) --e;
    return s.substr(b, e - b);
}
}  // namespace

GDEX_TEST(string_utils, trim_strips_both_ends) {
    GDEX_EXPECT_STR_EQ(trim("  hello  "), "hello");
}

GDEX_TEST(string_utils, trim_empty_returns_empty) {
    GDEX_EXPECT_STR_EQ(trim("    "), "");
}

GDEX_TEST(string_utils, trim_preserves_internal_spaces) {
    GDEX_EXPECT_STR_EQ(trim("  a b c  "), "a b c");
}

GDEX_TEST(string_utils, trim_no_op_on_clean_input) {
    GDEX_EXPECT_STR_EQ(trim("hello"), "hello");
}

#endif // GDEXTEST_ENABLED
