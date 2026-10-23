// The requests p2gen sends: one per target of the paths file, built once and never changed, so a
// pointer into them stays valid for the whole run (an overlapped send may outlive its connection).
// Pure code except read_file.
#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace p2gen {

class Requests {
public:
    std::size_t size() const noexcept { return offset_.empty() ? 0 : offset_.size() - 1; }
    std::string_view get(std::size_t i) const noexcept {
        return std::string_view(bytes_).substr(offset_[i], offset_[i + 1] - offset_[i]);
    }

private:
    friend std::string build_requests(std::string_view, const std::string&, int, Requests&);
    std::string bytes_;
    std::vector<std::size_t> offset_;  // size() + 1 entries
};

// Builds "GET <target> HTTP/1.1\r\nHost: <host>:<port>\r\n\r\n" for each non-blank line of
// targets_text (a trailing CR is dropped). A target must start with '/', hold no space or control
// byte, and be at most 8192 bytes. Returns an error text, or an empty string on success; a text
// with no target is an error.
std::string build_requests(std::string_view targets_text, const std::string& host, int port, Requests& out);

// The whole file into text. Returns an error text, or an empty string on success.
std::string read_file(const std::string& path, std::string& text);

}  // namespace p2gen
