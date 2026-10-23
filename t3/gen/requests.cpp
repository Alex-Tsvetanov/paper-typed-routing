#include "requests.hpp"

#include <fstream>
#include <utility>

namespace p2gen {

namespace {
constexpr std::size_t kMaxTarget = 8192;
}

std::string build_requests(std::string_view text, const std::string& host, int port, Requests& out) {
    const std::string tail = " HTTP/1.1\r\nHost: " + host + ":" + std::to_string(port) + "\r\n\r\n";
    Requests r;
    r.offset_.push_back(0);
    std::size_t pos = 0;
    while (pos < text.size()) {
        std::size_t eol = text.find('\n', pos);
        if (eol == std::string_view::npos) {
            eol = text.size();
        }
        std::string_view line = text.substr(pos, eol - pos);
        pos = eol + 1;
        while (!line.empty() && line.back() == '\r') {
            line.remove_suffix(1);
        }
        if (line.empty()) {
            continue;  // blank lines are not targets
        }
        if (line.front() != '/') {
            return "a request target must start with '/': " + std::string(line.substr(0, 80));
        }
        if (line.size() > kMaxTarget) {
            return "a request target is longer than 8192 bytes";
        }
        for (const char c : line) {
            const auto u = static_cast<unsigned char>(c);
            if (u <= ' ' || u == 0x7f) {
                return "a request target has a space or control byte: " + std::string(line.substr(0, 80));
            }
        }
        r.bytes_.append("GET ").append(line).append(tail);
        r.offset_.push_back(r.bytes_.size());
    }
    if (r.size() == 0) {
        return "the paths file has no targets";
    }
    out = std::move(r);
    return {};
}

std::string read_file(const std::string& path, std::string& text) {
    std::ifstream f(path, std::ios::binary);
    if (!f) {
        return "cannot open " + path;
    }
    f.seekg(0, std::ios::end);
    const std::streamoff size = f.tellg();
    f.seekg(0, std::ios::beg);
    if (!f || size < 0) {
        return "cannot read " + path;
    }
    text.resize(static_cast<std::size_t>(size));
    f.read(text.data(), size);
    if (!f) {
        return "cannot read " + path;
    }
    return {};
}

}  // namespace p2gen
