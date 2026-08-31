// Engine-boundary string coercion helpers (plan: GDEX_EXPECT_STR_* across types).
//
// This header is an engine-boundary header like engine.h / runner.h: it imports
// godot-cpp. Pure C++ test bodies must NOT include it. assert.h already defines
// the std::string / const char* overloads of to_std_string inline; this header
// ONLY adds the godot::String overload. The GDEX_EXPECT_STR_* macros call
// ::gdextest::to_std_string, which resolves at the macro-expansion site: suites
// that include strings.h (after assert.h) get the godot::String overload; pure
// suites resolve to the std overloads and never link against godot-cpp symbols.
#pragma once

#include <string>

#include <godot_cpp/variant/string.hpp>

namespace gdextest {

// UTF-8 conversion, the same policy the runner uses for engine strings.
inline std::string to_std_string(const godot::String &value) {
    return std::string(value.utf8().get_data());
}

inline std::string to_std_string(const std::string &value) {
    return value;
}

inline std::string to_std_string(const char *value) {
    return value ? std::string(value) : std::string("(null)");
}

} // namespace gdextest
