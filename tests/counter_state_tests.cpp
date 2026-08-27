// Host suite #2 (plan §14 M1: "stateful"). Exercises a small state machine — the
// §12 "state" category. A trivial counter stands in for a real extension module
// until one exists; the point is to prove fixture-style per-test state isolation.
#ifdef GDEXTEST_ENABLED

#include "gdextest/assert.h"
#include "gdextest/registry.h"

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

GDEX_TEST(counter, starts_at_zero_unbumped) {
    Counter c;
    GDEX_EXPECT_EQ(c.value(), 0);
    GDEX_EXPECT_FALSE(c.was_bumped());
}

GDEX_TEST(counter, bump_increments_and_sets_flag) {
    Counter c;
    c.bump();
    GDEX_EXPECT_EQ(c.value(), 1);
    GDEX_EXPECT_TRUE(c.was_bumped());
}

GDEX_TEST(counter, multiple_bumps_accumulate) {
    Counter c;
    for (int i = 0; i < 5; ++i) c.bump();
    GDEX_EXPECT_EQ(c.value(), 5);
}

GDEX_TEST(counter, reset_clears_state) {
    Counter c;
    c.bump(); c.bump();
    c.reset();
    GDEX_EXPECT_EQ(c.value(), 0);
    GDEX_EXPECT_FALSE(c.was_bumped());
}

#endif // GDEXTEST_ENABLED
