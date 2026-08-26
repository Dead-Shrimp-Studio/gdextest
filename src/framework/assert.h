// Assertion macros + value stringify<T> (plan §5.3). Engine types appear only at the
// value-formatting boundary (String/Variant/etc.); the core stays std::string.
//
// All macros record failures via TestContext::fail and continue (never throw), except
// GDEX_ABORT_TEST which throws TestAborted caught inside the runner's own frame.
#pragma once

#include <cmath>
#include <cstdio>
#include <sstream>
#include <string>
#include <type_traits>
#include <utility>

#include "context.h"

namespace gdextest {

// --- stringify<T> ----------------------------------------------------------
// Default: stream the value (works for arithmetic, std::string, anything with operator<<).
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

} // namespace gdextest

// --- Macros ----------------------------------------------------------------
// Each macro captures the current TestContext via `ctx` (a name the framework's runner
// injects into each test body). Suite authors write GDX_EXPECT_* exactly as documented.

#define GDEX_RECORD_(msg) (ctx).fail(__FILE__, __LINE__, (msg))
#define GDEX_RECORD_EXPR_(expr, msg) GDEX_RECORD_(std::string(#expr) + " — " + (msg))

#define GDEX_EXPECT(cond) do { if (!(cond)) GDEX_RECORD_EXPR_(cond, "condition false"); } while (0)
#define GDEX_EXPECT_TRUE(cond)  GDEX_EXPECT(cond)
#define GDEX_EXPECT_FALSE(cond) do { if ((cond)) GDEX_RECORD_EXPR_(cond, "condition true"); } while (0)

#define GDEX_EXPECT_EQ(a, b) do { \
    if (!((a) == (b))) GDEX_RECORD_(::gdextest::fmt_eq(#a, #b, (a), (b))); } while (0)
#define GDEX_EXPECT_NE(a, b) do { \
    if (((a) == (b))) GDEX_RECORD_(::gdextest::fmt_cmp("!=", #a, #b, (a), (b))); } while (0)
#define GDEX_EXPECT_LT(a, b) do { \
    if (!((a) <  (b))) GDEX_RECORD_(::gdextest::fmt_cmp("<",  #a, #b, (a), (b))); } while (0)
#define GDEX_EXPECT_LE(a, b) do { \
    if (!((a) <= (b))) GDEX_RECORD_(::gdextest::fmt_cmp("<=", #a, #b, (a), (b))); } while (0)
#define GDEX_EXPECT_GT(a, b) do { \
    if (!((a) >  (b))) GDEX_RECORD_(::gdextest::fmt_cmp(">",  #a, #b, (a), (b))); } while (0)
#define GDEX_EXPECT_GE(a, b) do { \
    if (!((a) >= (b))) GDEX_RECORD_(::gdextest::fmt_cmp(">=", #a, #b, (a), (b))); } while (0)

#define GDEX_EXPECT_NEAR(a, b, eps) do { \
    if (std::abs(static_cast<double>((a)) - static_cast<double>((b))) > static_cast<double>(eps)) \
        GDEX_RECORD_(::gdextest::fmt_cmp("near", #a, #b, (a), (b))); } while (0)

#define GDEX_EXPECT_STR_EQ(a, b) do { \
    if (std::string(a) != std::string(b)) GDEX_RECORD_(::gdextest::fmt_eq(#a, #b, std::string(a), std::string(b))); } while (0)
#define GDEX_EXPECT_STR_CONTAINS(hay, needle) do { \
    if (std::string(hay).find(needle) == std::string::npos) \
        GDEX_RECORD_(std::string("expected ") + #hay + " to contain " + #needle); } while (0)

#define GDEX_EXPECT_NULL(ptr)    do { if ((ptr) != nullptr) GDEX_RECORD_EXPR_(ptr, "expected null"); } while (0)
#define GDEX_EXPECT_NOT_NULL(ptr) do { if ((ptr) == nullptr) GDEX_RECORD_EXPR_(ptr, "expected non-null"); } while (0)

#define GDEX_FAIL(msg) do { GDEX_RECORD_(std::string(msg)); } while (0)
#define GDEX_ABORT_TEST(msg) \
    ::gdextest::TestContext::abort_test(__FILE__, __LINE__, (msg))

// Skips the current test for a runtime reason and stops the body. The test is
// recorded in the `skip` totals (not pass/fail) with the given reason. Usually
// called from an early guard when a precondition/fixture/service is unavailable.
#define GDEX_SKIP(msg) \
    ::gdextest::TestContext::skip(__FILE__, __LINE__, (msg))
