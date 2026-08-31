#ifndef GDEXTEST_SIGNALS_H
#define GDEXTEST_SIGNALS_H

#include <string>
#include <unordered_map>
#include <vector>

#include <godot_cpp/core/object.hpp>
#include <godot_cpp/variant/variant.hpp>

using namespace godot;

namespace gdextest {

struct SignalData {
    uint64_t target_id = 0;
    String signal_name;
    int expected_count = 0;
    int actual_count = 0;
    std::vector<std::vector<Variant>> emission_history;
};

class SignalMonitor : public Object {
    GDCLASS(SignalMonitor, Object)

protected:

    static void _bind_methods();

private:

    std::unordered_map<std::string, SignalData> signals;

    static std::string make_key(uint64_t p_id, const String &p_signal_name);

public:

    SignalMonitor();
    ~SignalMonitor();

    // GDExtension VarArg receiver for dynamic signal invocations
    Variant _on_signal_fired(const Variant **p_args, GDExtensionInt p_arg_count, GDExtensionCallError &r_error);

    // Monitoring Management (Supports Fluent Chaining)
    void add(Object *p_target, const String &p_signal_name, int p_expected = 0);
    void add_all(Object *p_target, const std::vector<String> &p_signals, int p_expected = 0);
    void remove(Object *p_target, const String &p_signal_name);
    void remove_all();

    // State Resetting
    void reset(Object *p_target, const String &p_signal_name);
    void reset_all();

    // Queries & Assertions
    bool was_emitted(Object *p_target, const String &p_signal_name) const;
    int get_emission_count(Object *p_target, const String &p_signal_name) const;
    std::vector<Variant> get_last_arguments(Object *p_target, const String &p_signal_name) const;
    Variant get_argument(Object *p_target, const String &p_signal_name, size_t p_emission_index, size_t p_arg_index) const;
    const std::vector<std::vector<Variant>> &get_emission_history(Object *p_target, const String &p_signal_name) const;

    // Overall Evaluation
    bool evaluate() const;
};

} // namespace gdextest

#endif