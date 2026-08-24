// Test case model, registry, and auto-registration. Pure C++; no Godot types —
// honors the "no Godot objects in static initializers" rule (plan §5.1, §15).
//
// Each test body receives a TestContext& named `ctx` (injected by the macro), so
// assertion macros reference `ctx` directly (plan §5.2 — chosen ctx-access model).
#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "config.h"
#include "context.h"

namespace gdextest {

// A test body takes its per-test context by reference; the runner constructs one
// per case and passes it in. This is the "runner injects ctx" model (plan §5.2).
using TestFn = void (*)(TestContext &);

struct TestCase {
    const char *suite;
    const char *name;
    TestFn fn;
    uint32_t tags;
    const char *file;
    int line;
};

// Glob patterns + negatives; mirrors googletest filter grammar (plan §5.4).
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

// Static registrar: the GDX_TEST macro constructs one of these; its ctor calls add().
struct Registrar {
    Registrar(const TestCase &tc) { TestRegistry::instance().add(tc); }
};

} // namespace gdextest

// Auto-registration macro. Declares a test fn taking TestContext& ctx, registers it
// via a static Registrar, then opens the body. `suite`/`name` must be identifiers.
// The body sees `ctx` in scope, so GDX_EXPECT_* macros resolve it by name.
#define GDX_TEST(suite, name)                                                        \
    static void gdx_test_##suite##_##name(::gdextest::TestContext &ctx);            \
    static const ::gdextest::Registrar gdx_reg_##suite##_##name{                     \
        ::gdextest::TestCase{ #suite, #name, &gdx_test_##suite##_##name,            \
                              ::gdextest::TAG_UNIT, __FILE__, __LINE__ } };        \
    static void gdx_test_##suite##_##name(::gdextest::TestContext &ctx)

// Tagged variant: GDX_TEST_T(suite, name, TAG_UNIT | TAG_SLOW, ...)
#define GDX_TEST_T(suite, name, tags)                                                \
    static void gdx_test_##suite##_##name(::gdextest::TestContext &ctx);             \
    static const ::gdextest::Registrar gdx_reg_##suite##_##name{                     \
        ::gdextest::TestCase{ #suite, #name, &gdx_test_##suite##_##name,            \
                              (tags), __FILE__, __LINE__ } };                        \
    static void gdx_test_##suite##_##name(::gdextest::TestContext &ctx)
