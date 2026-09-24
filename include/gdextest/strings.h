
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
