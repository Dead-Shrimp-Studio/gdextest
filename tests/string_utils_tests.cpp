
#ifdef GDEXTEST_ENABLED

#include <string>

#include <godot_cpp/variant/string.hpp>

#include "gdextest/assert.h"
#include "gdextest/registry.h"

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

GDEX_TEST(string_utils, string_conversion_std_godot) {

    // Combinations of godot::String and std::string
    GDEX_EXPECT_STR_CONTAINS("hello world", godot::String("world"));
    GDEX_EXPECT_STR_CONTAINS(godot::String("hello world"), "hello");

    GDEX_EXPECT_STR_EQ("world", godot::String("world"));
    GDEX_EXPECT_STR_EQ(godot::String("world"), "world");

    GDEX_EXPECT_STR_NE("world", godot::String("hello"));
    GDEX_EXPECT_STR_NE(godot::String("hello"), "world");
}

#endif // GDEXTEST_ENABLED
