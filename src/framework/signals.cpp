#include "gdextest/signals.h"
#include "gdextest/strings.h"

#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/classes/object.hpp>

using namespace godot;

static const std::vector<std::vector<Variant>> EMPTY_HISTORY;

std::string gdextest::SignalMonitor::make_key(uint64_t p_id, const String &p_signal_name)
{
    return std::to_string(p_id) + ":" + gdextest::to_std_string(p_signal_name);
}

void gdextest::SignalMonitor::_bind_methods()
{
    MethodInfo mi;
    mi.name = "_on_signal_fired";
    ClassDB::bind_vararg_method(METHOD_FLAG_NORMAL, "_on_signal_fired", &SignalMonitor::_on_signal_fired, mi);
}

gdextest::SignalMonitor::SignalMonitor() {}

gdextest::SignalMonitor::~SignalMonitor()
{
    remove_all();
}

Variant gdextest::SignalMonitor::_on_signal_fired(const Variant **p_args, GDExtensionInt p_arg_count, GDExtensionCallError &r_error)
{
    // Bound arguments are appended to the end: [target_id, signal_name]
    if (p_arg_count < 2) {
        return Variant();
    }

    uint64_t target_id = *p_args[p_arg_count - 2];
    String signal_name = *p_args[p_arg_count - 1];
    std::string key = make_key(target_id, signal_name);

    auto it = signals.find(key);
    if (it != signals.end()) {
        it->second.actual_count++;

        // Collect argument payload (excluding the 2 bound metadata arguments)
        GDExtensionInt payload_count = p_arg_count - 2;
        std::vector<Variant> args_record;
        args_record.reserve(payload_count);

        for (GDExtensionInt i = 0; i < payload_count; ++i) {
            args_record.push_back(*p_args[i]);
        }

        it->second.emission_history.push_back(std::move(args_record));
    }

    return Variant();
}

void gdextest::SignalMonitor::add(Object *p_target, const String &p_signal_name, int p_expected)
{
    if (!p_target) {
        return;
    }

    uint64_t target_id = p_target->get_instance_id();
    std::string key = make_key(target_id, p_signal_name);

    SignalData data;
    data.target_id = target_id;
    data.signal_name = p_signal_name;
    data.expected_count = p_expected;
    data.actual_count = 0;

    signals[key] = data;

    Callable callable = Callable(this, "_on_signal_fired").bind(target_id, p_signal_name);
    if (!p_target->is_connected(p_signal_name, callable)) {
        p_target->connect(p_signal_name, callable);
    }
}

void gdextest::SignalMonitor::add_all(Object *p_target, const std::vector<String> &p_signals, int p_expected)
{
    for (const String &sig : p_signals) {
        add(p_target, sig, p_expected);
    }
}

void gdextest::SignalMonitor::remove(Object *p_target, const String &p_signal_name)
{
    if (!p_target) {
        return;
    }

    uint64_t target_id = p_target->get_instance_id();
    std::string key = make_key(target_id, p_signal_name);

    auto it = signals.find(key);
    if (it != signals.end()) {
        Callable callable = Callable(this, "_on_signal_fired").bind(target_id, p_signal_name);
        if (p_target->is_connected(p_signal_name, callable)) {
            p_target->disconnect(p_signal_name, callable);
        }
        signals.erase(it);
    }
}

void gdextest::SignalMonitor::remove_all()
{
    for (auto &pair : signals) {
        Object *target = ObjectDB::get_instance(ObjectID(pair.second.target_id));
        if (target) {
            Callable callable = Callable(this, "_on_signal_fired").bind(pair.second.target_id, pair.second.signal_name);
            if (target->is_connected(pair.second.signal_name, callable)) {
                target->disconnect(pair.second.signal_name, callable);
            }
        }
    }
    signals.clear();
}

void gdextest::SignalMonitor::reset(Object *p_target, const String &p_signal_name)
{
    if (!p_target) {
        return;
    }

    std::string key = make_key(p_target->get_instance_id(), p_signal_name);
    auto it = signals.find(key);
    if (it != signals.end()) {
        it->second.actual_count = 0;
        it->second.emission_history.clear();
    }
}

void gdextest::SignalMonitor::reset_all()
{
    for (auto &pair : signals) {
        pair.second.actual_count = 0;
        pair.second.emission_history.clear();
    }
}

bool gdextest::SignalMonitor::was_emitted(Object *p_target, const String &p_signal_name) const
{
    return get_emission_count(p_target, p_signal_name) > 0;
}

int gdextest::SignalMonitor::get_emission_count(Object *p_target, const String &p_signal_name) const
{
    if (!p_target) {
        return 0;
    }

    std::string key = make_key(p_target->get_instance_id(), p_signal_name);
    auto it = signals.find(key);
    return (it != signals.end()) ? it->second.actual_count : 0;
}

std::vector<Variant> gdextest::SignalMonitor::get_last_arguments(Object *p_target, const String &p_signal_name) const
{
    if (!p_target) {
        return {};
    }

    std::string key = make_key(p_target->get_instance_id(), p_signal_name);
    auto it = signals.find(key);
    if (it != signals.end() && !it->second.emission_history.empty()) {
        return it->second.emission_history.back();
    }
    return {};
}

Variant gdextest::SignalMonitor::get_argument(Object *p_target, const String &p_signal_name, size_t p_emission_index, size_t p_arg_index) const
{
    if (!p_target) {
        return Variant();
    }

    std::string key = make_key(p_target->get_instance_id(), p_signal_name);
    auto it = signals.find(key);
    if (it != signals.end() && p_emission_index < it->second.emission_history.size()) {
        const auto &args = it->second.emission_history[p_emission_index];
        if (p_arg_index < args.size()) {
            return args[p_arg_index];
        }
    }
    return Variant();
}

const std::vector<std::vector<Variant>> &gdextest::SignalMonitor::get_emission_history(Object *p_target, const String &p_signal_name) const
{
    if (!p_target) {
        return EMPTY_HISTORY;
    }

    std::string key = make_key(p_target->get_instance_id(), p_signal_name);
    auto it = signals.find(key);
    return (it != signals.end()) ? it->second.emission_history : EMPTY_HISTORY;
}

bool gdextest::SignalMonitor::evaluate() const
{
    for (const auto &pair : signals) {
        if (pair.second.actual_count != pair.second.expected_count) {
            return false;
        }
    }
    return true;
}