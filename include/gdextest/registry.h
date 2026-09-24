
#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "async.h"
#include "config.h"
#include "context.h"

namespace gdextest {

using TestFn = void (*)(TestContext &);
using AsyncTestFn = Task (*)(TestContext &);

struct TestCase {
    const char *suite;
    const char *name;
    TestFn fn;            // synchronous body; null for async tests
    AsyncTestFn async_fn; // coroutine body; null for sync tests
    uint32_t tags;
    const char *file;
    int line;
};

// Glob patterns + negatives; mirrors googletest filter grammar 
struct Filter {
    // Each entry: positive glob, or negative ("-glob"). Empty filter = all tests.
    std::vector<std::string> patterns;
    uint32_t include_tags = 0;   // 0 = any tag
    uint32_t exclude_tags = 0;
    int shard_index = 0;         // 0-based
    int shard_count = 1;         // 1 = no sharding
    bool shuffle = false;
    unsigned shuffle_seed = 0;
    bool list_only = false;      // print selected, don't run
};

class TestRegistry {
public:
    static TestRegistry &instance();   // function-local static — plain C++ only
    void add(TestCase tc);
    const std::vector<TestCase> &all() const;
    // Returns the selected tests in run order (after filter + shard + shuffle).
    std::vector<const TestCase *> select(const Filter &f) const;

private:
    TestRegistry() = default;
    std::vector<TestCase> cases_;
};

// Static registrar: the GDEX_TEST macro constructs one of these; its ctor calls add().
struct Registrar {
    Registrar(const TestCase &tc) { TestRegistry::instance().add(tc); }
};

} // namespace gdextest

// Auto-registration macro. Declares a test fn taking TestContext& ctx, registers it
// via a static Registrar, then opens the body. `suite`/`name` must be identifiers.
// The body sees `ctx` in scope, so GDX_EXPECT_* macros resolve it by name.
#define GDEX_TEST(suite, name)                                                        \
    static void gdx_test_##suite##_##name(::gdextest::TestContext &ctx);            \
    static const ::gdextest::Registrar gdx_reg_##suite##_##name{                     \
        ::gdextest::TestCase{ #suite, #name, &gdx_test_##suite##_##name, nullptr,   \
                              ::gdextest::TAG_UNIT, __FILE__, __LINE__ } };        \
    static void gdx_test_##suite##_##name(::gdextest::TestContext &ctx)

// Tagged variant: GDEX_TEST_T(suite, name, TAG_UNIT | TAG_SLOW, ...)
// The Registrar initializer runs inside an immediately-invoked lambda that brings
// the gdextest namespace into scope, so bare tag names (TAG_INTEGRATION, …) resolve
// exactly as the docs describe, no matter what namespace the caller is in.
#define GDEX_TEST_T(suite, name, tags)                                                \
    static void gdx_test_##suite##_##name(::gdextest::TestContext &ctx);             \
    static const ::gdextest::Registrar gdx_reg_##suite##_##name{ []() {              \
        using namespace ::gdextest;                                                   \
        return ::gdextest::TestCase{ #suite, #name, &gdx_test_##suite##_##name,      \
                                     nullptr, (tags), __FILE__, __LINE__ };          \
    }() };                                                                             \
    static void gdx_test_##suite##_##name(::gdextest::TestContext &ctx)

// Async variant: GDEX_TEST_ASYNC(suite, name) registers a coroutine body tagged
// TAG_ASYNC. The body may `co_await ctx.await_frames(n)` / `ctx.await_timer_ms(ms)`
// to suspend across engine frames; the runner's frame pump resumes it. 
// The body must not use a bare `return;` — use `co_return;` instead.
#define GDEX_TEST_ASYNC(suite, name)                                                   \
    static ::gdextest::Task gdx_test_##suite##_##name(::gdextest::TestContext &ctx);  \
    static const ::gdextest::Registrar gdx_reg_##suite##_##name{                      \
        ::gdextest::TestCase{ #suite, #name, nullptr, &gdx_test_##suite##_##name,     \
                              ::gdextest::TAG_ASYNC, __FILE__, __LINE__ } };         \
    static ::gdextest::Task gdx_test_##suite##_##name(::gdextest::TestContext &ctx)

// Tagged async variant (bare tag names resolve like GDEX_TEST_T).
#define GDEX_TEST_ASYNC_T(suite, name, tags)                                           \
    static ::gdextest::Task gdx_test_##suite##_##name(::gdextest::TestContext &ctx);  \
    static const ::gdextest::Registrar gdx_reg_##suite##_##name{ []() {               \
        using namespace ::gdextest;                                                   \
        return ::gdextest::TestCase{ #suite, #name, nullptr,                          \
                                     &gdx_test_##suite##_##name, (tags),             \
                                     __FILE__, __LINE__ };                           \
    }() };                                                                             \
    static ::gdextest::Task gdx_test_##suite##_##name(::gdextest::TestContext &ctx)
