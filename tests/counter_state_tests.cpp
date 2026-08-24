// Host suite #2 (plan §14 M1: "stateful"). Exercises a small state machine — the
// §12 "state" category. A trivial counter stands in for a real extension module
// until one exists; the point is to prove fixture-style per-test state isolation.
#ifdef GDX_TESTS_ENABLED

#include "framework/assert.h"
#include "framework/registry.h"

namespace {

class Counter {
public:
    void reset() { value_ = 0; bumped_ = false; }
    void bump() { ++value_; bumped_ = true; }
    int value() const { return value_; }
    bool was_bumped() const { return bumped_; }
private:
    int value_ = 0;
    bool bumped_ = false;
};

}  // namespace

GDX_TEST(counter, starts_at_zero_unbumped) {
    Counter c;
    GDX_EXPECT_EQ(c.value(), 0);
    GDX_EXPECT_FALSE(c.was_bumped());
}

GDX_TEST(counter, bump_increments_and_sets_flag) {
    Counter c;
    c.bump();
    GDX_EXPECT_EQ(c.value(), 1);
    GDX_EXPECT_TRUE(c.was_bumped());
}

GDX_TEST(counter, multiple_bumps_accumulate) {
    Counter c;
    for (int i = 0; i < 5; ++i) c.bump();
    GDX_EXPECT_EQ(c.value(), 5);
}

GDX_TEST(counter, reset_clears_state) {
    Counter c;
    c.bump(); c.bump();
    c.reset();
    GDX_EXPECT_EQ(c.value(), 0);
    GDX_EXPECT_FALSE(c.was_bumped());
}

#endif // GDX_TESTS_ENABLED
