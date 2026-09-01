// Assertion macros + value stringify<T>. Engine types appear only at the
// value-formatting boundary (String/Variant/etc.); the core stays std::string.
#pragma once

#include <cmath>
#include <cstdio>
#include <exception>
#include <sstream>
#include <string>
#include <type_traits>
#include <utility>

#include "context.h"
#include "strings.h"
#include "signals.h"

namespace gdextest {

// --- stringify<T> ----------------------------------------------------------
template <typename T>
std::string stringify(const T &v) {
    std::ostringstream os;
    os << v;
    return os.str();
}
inline std::string stringify(bool v) { return v ? "true" : "false"; }
inline std::string stringify(const char *v) {
    return v ? std::string("\"") + v + "\"" : std::string("(null)");
}

// C++ helpers for formatting pairs/expected-vs-actual in comparison macros.
template <typename A, typename B>
inline std::string fmt_eq(const char *aexpr, const char *bexpr, const A &a, const B &b) {
    return std::string("expected ") + aexpr + " == " + bexpr
         + "\n  expected: " + stringify(a)
         + "\n  actual:   " + stringify(b);
}

template <typename A, typename B>
inline std::string fmt_cmp(const char *op, const char *aexpr, const char *bexpr,
                           const A &a, const B &b) {
    return std::string("expected (") + aexpr + ") " + op + " (" + bexpr + ")"
         + "\n  lhs: " + stringify(a)
         + "\n  rhs: " + stringify(b);
}

inline bool str_starts_with(const std::string &str, const std::string &prefix) {
    return str.rfind(prefix, 0) == 0;
}

inline bool str_ends_with(const std::string &str, const std::string &suffix) {
    if (suffix.size() > str.size()) return false;
    return str.compare(str.size() - suffix.size(), suffix.size(), suffix) == 0;
}

} // namespace gdextest

// --- Internal Macro Support -------------------------------------------------
#define GDEX_RECORD_(msg) (ctx).fail(__FILE__, __LINE__, (msg))
#define GDEX_RECORD_EXPR_(expr, msg) GDEX_RECORD_(std::string(#expr) + " — " + (msg))

// --- Explicit & Conditional Failures ---------------------------------------
#define GDEX_FAIL(msg) do { GDEX_RECORD_(std::string(msg)); } while (0)

#define GDEX_FAIL_IF(cond, msg) do { \
    if (cond) GDEX_RECORD_(std::string("failed on (" #cond "): ") + (msg)); } while (0)

#define GDEX_FAIL_UNLESS(cond, msg) do { \
    if (!(cond)) GDEX_RECORD_(std::string("failed on !(" #cond "): ") + (msg)); } while (0)

#define GDEX_ABORT_TEST(msg) \
    ::gdextest::TestContext::abort_test(__FILE__, __LINE__, (msg))

#define GDEX_SKIP(msg) \
    ::gdextest::TestContext::skip(__FILE__, __LINE__, (msg))

// --- Non-Fatal Expectations (`EXPECT_*`) -----------------------------------
#define GDEX_EXPECT(cond) do { if (!(cond)) GDEX_RECORD_EXPR_(cond, "condition false"); } while (0)
#define GDEX_EXPECT_TRUE(cond)  GDEX_EXPECT(cond)
#define GDEX_EXPECT_FALSE(cond) do { if ((cond)) GDEX_RECORD_EXPR_(cond, "condition true"); } while (0)

#define GDEX_EXPECT_EQ(a, b) do { \
    const auto &gdx_a = (a); const auto &gdx_b = (b); \
    if (!(gdx_a == gdx_b)) GDEX_RECORD_(::gdextest::fmt_eq(#a, #b, gdx_a, gdx_b)); } while (0)

#define GDEX_EXPECT_NE(a, b) do { \
    const auto &gdx_a = (a); const auto &gdx_b = (b); \
    if (gdx_a == gdx_b) GDEX_RECORD_(::gdextest::fmt_cmp("!=", #a, #b, gdx_a, gdx_b)); } while (0)

#define GDEX_EXPECT_LT(a, b) do { \
    const auto &gdx_a = (a); const auto &gdx_b = (b); \
    if (!(gdx_a < gdx_b)) GDEX_RECORD_(::gdextest::fmt_cmp("<", #a, #b, gdx_a, gdx_b)); } while (0)

#define GDEX_EXPECT_LE(a, b) do { \
    const auto &gdx_a = (a); const auto &gdx_b = (b); \
    if (!(gdx_a <= gdx_b)) GDEX_RECORD_(::gdextest::fmt_cmp("<=", #a, #b, gdx_a, gdx_b)); } while (0)

#define GDEX_EXPECT_GT(a, b) do { \
    const auto &gdx_a = (a); const auto &gdx_b = (b); \
    if (!(gdx_a > gdx_b)) GDEX_RECORD_(::gdextest::fmt_cmp(">", #a, #b, gdx_a, gdx_b)); } while (0)

#define GDEX_EXPECT_GE(a, b) do { \
    const auto &gdx_a = (a); const auto &gdx_b = (b); \
    if (!(gdx_a >= gdx_b)) GDEX_RECORD_(::gdextest::fmt_cmp(">=", #a, #b, gdx_a, gdx_b)); } while (0)

#define GDEX_EXPECT_NEAR(a, b, eps) do { \
    const auto &gdx_a = (a); const auto &gdx_b = (b); const auto &gdx_eps = (eps); \
    if (std::abs(static_cast<double>(gdx_a) - static_cast<double>(gdx_b)) > static_cast<double>(gdx_eps)) \
        GDEX_RECORD_(::gdextest::fmt_cmp("near", #a, #b, gdx_a, gdx_b)); } while (0)

#define GDEX_EXPECT_NULL(ptr) do { \
    const auto &gdx_ptr = (ptr); \
    if (gdx_ptr != nullptr) GDEX_RECORD_(std::string(#ptr) + " — expected null"); } while (0)

#define GDEX_EXPECT_NOT_NULL(ptr) do { \
    const auto &gdx_ptr = (ptr); \
    if (gdx_ptr == nullptr) GDEX_RECORD_(std::string(#ptr) + " — expected non-null"); } while (0)

// --- Fatal Assertions (`ASSERT_*`) -----------------------------------------
// Unlike EXPECT, ASSERT terminates the test immediately if the check fails.
#define GDEX_ASSERT_TRUE(cond) do { \
    if (!(cond)) { GDEX_RECORD_EXPR_(cond, "assert condition false"); GDEX_ABORT_TEST(#cond); } } while (0)

#define GDEX_ASSERT_FALSE(cond) do { \
    if ((cond)) { GDEX_RECORD_EXPR_(cond, "assert condition true"); GDEX_ABORT_TEST(#cond); } } while (0)

#define GDEX_ASSERT_EQ(a, b) do { \
    const auto &gdx_a = (a); const auto &gdx_b = (b); \
    if (!(gdx_a == gdx_b)) { GDEX_RECORD_(::gdextest::fmt_eq(#a, #b, gdx_a, gdx_b)); GDEX_ABORT_TEST("equality assertion failed"); } } while (0)

#define GDEX_ASSERT_NE(a, b) do { \
    const auto &gdx_a = (a); const auto &gdx_b = (b); \
    if (gdx_a == gdx_b) { GDEX_RECORD_(::gdextest::fmt_cmp("!=", #a, #b, gdx_a, gdx_b)); GDEX_ABORT_TEST("inequality assertion failed"); } } while (0)

#define GDEX_ASSERT_NOT_NULL(ptr) do { \
    const auto &gdx_ptr = (ptr); \
    if (gdx_ptr == nullptr) { GDEX_RECORD_(std::string(#ptr) + " — expected non-null"); GDEX_ABORT_TEST(#ptr " was null"); } } while (0)

#define GDEX_ASSERT_NULL(ptr) do { \
    const auto &gdx_ptr = (ptr); \
    if (gdx_ptr != nullptr) { GDEX_RECORD_(std::string(#ptr) + " — expected null"); GDEX_ABORT_TEST(#ptr " was not null"); } } while (0)

// --- String Assertions ------------------------------------------------------
#define GDEX_EXPECT_STR_EQ(a, b) do { \
    const auto &gdx_a = (a); const auto &gdx_b = (b); \
    const std::string gdx_a_string = ::gdextest::to_std_string(gdx_a); \
    const std::string gdx_b_string = ::gdextest::to_std_string(gdx_b); \
    if (gdx_a_string != gdx_b_string) GDEX_RECORD_(::gdextest::fmt_eq(#a, #b, gdx_a_string, gdx_b_string)); } while (0)

#define GDEX_EXPECT_STR_NE(a, b) do { \
    const auto &gdx_a = (a); const auto &gdx_b = (b); \
    const std::string gdx_a_string = ::gdextest::to_std_string(gdx_a); \
    const std::string gdx_b_string = ::gdextest::to_std_string(gdx_b); \
    if (gdx_a_string == gdx_b_string) GDEX_RECORD_(::gdextest::fmt_cmp("!=", #a, #b, gdx_a_string, gdx_b_string)); } while (0)

#define GDEX_EXPECT_STR_CONTAINS(hay, needle) do { \
    const auto &gdx_hay = (hay); const auto &gdx_needle = (needle); \
    if (::gdextest::to_std_string(gdx_hay).find(::gdextest::to_std_string(gdx_needle)) == std::string::npos) \
        GDEX_RECORD_(std::string("expected ") + #hay + " to contain " + #needle); } while (0)

#define GDEX_EXPECT_STR_STARTS_WITH(hay, prefix) do { \
    const std::string gdx_hay = ::gdextest::to_std_string(hay); \
    const std::string gdx_prefix = ::gdextest::to_std_string(prefix); \
    if (!::gdextest::str_starts_with(gdx_hay, gdx_prefix)) \
        GDEX_RECORD_(std::string("expected '") + gdx_hay + "' to start with '" + gdx_prefix + "'"); } while (0)

#define GDEX_EXPECT_STR_ENDS_WITH(hay, suffix) do { \
    const std::string gdx_hay = ::gdextest::to_std_string(hay); \
    const std::string gdx_suffix = ::gdextest::to_std_string(suffix); \
    if (!::gdextest::str_ends_with(gdx_hay, gdx_suffix)) \
        GDEX_RECORD_(std::string("expected '") + gdx_hay + "' to end with '" + gdx_suffix + "'"); } while (0)

#define GDEX_EXPECT_STR_EMPTY(str) do { \
    const std::string gdx_s = ::gdextest::to_std_string(str); \
    if (!gdx_s.empty()) GDEX_RECORD_(std::string(#str) + " — expected empty string, got: \"" + gdx_s + "\""); } while (0)

#define GDEX_EXPECT_STR_NOT_EMPTY(str) do { \
    const std::string gdx_s = ::gdextest::to_std_string(str); \
    if (gdx_s.empty()) GDEX_RECORD_(std::string(#str) + " — expected non-empty string"); } while (0)

// --- Exception Assertions ---------------------------------------------------
#define GDEX_EXPECT_THROW(statement, expected_exception) do { \
    bool gdx_threw_expected = false; \
    try { \
        statement; \
    } catch (const expected_exception &) { \
        gdx_threw_expected = true; \
    } catch (...) { \
        GDEX_RECORD_(std::string(#statement) + " threw unexpected exception type instead of " #expected_exception); \
        gdx_threw_expected = true; \
    } \
    if (!gdx_threw_expected) GDEX_RECORD_(std::string(#statement) + " expected to throw " #expected_exception); \
} while (0)

#define GDEX_EXPECT_NO_THROW(statement) do { \
    try { \
        statement; \
    } catch (const std::exception &e) { \
        GDEX_RECORD_(std::string(#statement) + " threw exception: " + e.what()); \
    } catch (...) { \
        GDEX_RECORD_(std::string(#statement) + " threw unknown exception"); \
    } \
} while (0)

#define GDEX_EXPECT_ANY_THROW(statement) do { \
    bool gdx_threw = false; \
    try { \
        statement; \
    } catch (...) { \
        gdx_threw = true; \
    } \
    if (!gdx_threw) GDEX_RECORD_(std::string(#statement) + " expected to throw an exception"); \
} while (0)