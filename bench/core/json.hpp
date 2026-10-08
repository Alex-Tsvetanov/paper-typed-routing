// A flat JSON object writer, enough for one result line.
#pragma once

#include <cmath>
#include <cstdio>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>

namespace rb {

class Json {
public:
    Json& str(std::string_view k, std::string_view v) {
        key(k);
        quote(v);
        return *this;
    }
    template <class T>
        requires std::is_arithmetic_v<T>
    Json& num(std::string_view k, T v) {
        key(k);
        number(static_cast<double>(v), std::is_integral_v<T>);
        return *this;
    }
    Json& boolean(std::string_view k, bool v) {
        key(k);
        s_ += v ? "true" : "false";
        return *this;
    }
    Json& null(std::string_view k) {
        key(k);
        s_ += "null";
        return *this;
    }
    Json& nums(std::string_view k, const std::vector<double>& v) {
        key(k);
        s_ += '[';
        for (std::size_t i = 0; i < v.size(); ++i) {
            if (i) s_ += ',';
            number(v[i], false);
        }
        s_ += ']';
        return *this;
    }
    Json& strs(std::string_view k, const std::vector<std::string>& v) {
        key(k);
        s_ += '[';
        for (std::size_t i = 0; i < v.size(); ++i) {
            if (i) s_ += ',';
            quote(v[i]);
        }
        s_ += ']';
        return *this;
    }
    // A pre-rendered JSON value.
    Json& raw(std::string_view k, std::string_view v) {
        key(k);
        s_ += v;
        return *this;
    }
    std::string done() const { return s_ + '}'; }

    static std::string quoted(std::string_view v) {
        Json j;
        j.s_.clear();
        j.quote(v);
        return j.s_;
    }

private:
    void key(std::string_view k) {
        if (s_.size() > 1) s_ += ',';
        quote(k);
        s_ += ':';
    }
    void number(double v, bool integral) {
        if (!std::isfinite(v)) {
            s_ += "null";
            return;
        }
        char buf[40];
        std::snprintf(buf, sizeof buf, integral ? "%.0f" : "%.9g", v);
        s_ += buf;
    }
    void quote(std::string_view v) {
        s_ += '"';
        for (const char ch : v) {
            const auto c = static_cast<unsigned char>(ch);
            if (c == '"' || c == '\\') {
                s_ += '\\';
                s_ += ch;
            } else if (c < 0x20) {
                char buf[8];
                std::snprintf(buf, sizeof buf, "\\u%04x", c);
                s_ += buf;
            } else {
                s_ += ch;
            }
        }
        s_ += '"';
    }

    std::string s_ = "{";
};

}  // namespace rb
