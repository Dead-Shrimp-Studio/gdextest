// Per-test result sink + owned-object tracking (plan §5.2). Pure C++ core.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace gdextest {

struct Failure {
    std::string file;
    int line = 0;
    std::string message;
};

class TestContext {
public:
    // Called by assertion macros (plan §5.2). Recorded, never thrown.
    void fail(const char *file, int line, std::string message) {
        failures_.push_back({file ? file : "", line, std::move(message)});
    }

    bool ok() const { return failures_.empty(); }
    int failure_count() const { return static_cast<int>(failures_.size()); }
    const std::vector<Failure> &failures() const { return failures_; }

    // Throw to abort the current test only (caught inside the runner's frame —
    // never crosses an engine callback boundary; plan §5.2). Throws only when
    // GDX_TESTS_ENABLED is active; otherwise a no-op.
    [[noreturn]] static void abort_test(const char *file, int line, std::string message);

    // Live engine access for integration tests. The handle is opaque here so the
    // core stays free of Godot types; engine-boundary accessors live in
    // framework/engine.h and cast this handle to the real Node/SceneTree.
    // Non-null only when the test runs through the real engine trigger.
    void set_engine(void *engine) { engine_ = engine; }
    void *engine_handle() const { return engine_; }

private:
    std::vector<Failure> failures_;

    // Live engine host (the tree node handed to run_all_and_quit), or null for
    // self/sub invocations.
    void *engine_ = nullptr;

    // Owned-object tracking (leak/UAF hooks; full impl lands at M4 per plan §7.4).
    // Declared now so the assertion macros can reference ctx.track_* without #ifdef churn.
public:
    void track_object(void * /*obj*/) { /* M4 */ }
    void track_ref(void * /*ref*/) { /* M4 */ }
};

} // namespace gdextest
