#include "framing.hpp"

#include <cstring>

namespace p2gen {

namespace {

bool is_digit(char c) noexcept {
    return c >= '0' && c <= '9';
}

char lower(char c) noexcept {
    return (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c;
}

// ASCII case-insensitive equality; locale independent.
bool iequals(std::string_view a, std::string_view b) noexcept {
    if (a.size() != b.size()) {
        return false;
    }
    for (std::size_t i = 0; i < a.size(); ++i) {
        if (lower(a[i]) != lower(b[i])) {
            return false;
        }
    }
    return true;
}

std::string_view trim(std::string_view s) noexcept {
    while (!s.empty() && (s.front() == ' ' || s.front() == '\t')) {
        s.remove_prefix(1);
    }
    while (!s.empty() && (s.back() == ' ' || s.back() == '\t')) {
        s.remove_suffix(1);
    }
    return s;
}

// Whether a Connection header value, a comma list of tokens, holds the token "close".
bool has_close_token(std::string_view value) noexcept {
    while (!value.empty()) {
        const std::size_t comma = value.find(',');
        const std::string_view token = trim(value.substr(0, comma));
        if (iequals(token, "close")) {
            return true;
        }
        if (comma == std::string_view::npos) {
            break;
        }
        value.remove_prefix(comma + 1);
    }
    return false;
}

// Content-Length is at most 18 digits, which cannot overflow 64 bits.
constexpr std::size_t kMaxLengthDigits = 18;

}  // namespace

void Framer::reset() noexcept {
    state_ = State::Head;
    answer_ = Answer{};
    head_.clear();
    seen_ = 0;
    match_ = false;
    fault_ = nullptr;
}

void Framer::set_fault(const char* why) noexcept {
    state_ = State::Bad;
    fault_ = why;
}

std::size_t Framer::feed(const char* p, std::size_t n) {
    std::size_t used = 0;
    if (state_ == State::Head) {
        used = feed_head(p, n);
    }
    if (state_ == State::Body && used < n) {
        used += feed_body(p + used, n - used);
    }
    return used;  // nothing once Done or Bad
}

std::size_t Framer::feed_head(const char* p, std::size_t n) {
    const std::size_t old = head_.size();
    if (old == 0) {
        // The usual case: the whole head is in this read, so it is parsed where it lies.
        const std::string_view chunk(p, n);
        const std::size_t end = chunk.find("\r\n\r\n");
        if (end != std::string_view::npos) {
            end_of_head(chunk.substr(0, end + 4));
            return end + 4;
        }
    }
    head_.append(p, n);
    // The terminator may straddle the old end and the new bytes.
    const std::size_t end = head_.find("\r\n\r\n", old >= 3 ? old - 3 : 0);
    if (end == std::string::npos) {
        if (head_.size() > kHeaderLimit) {
            set_fault("head too large");
            head_.clear();
        }
        return n;
    }
    head_.resize(end + 4);
    end_of_head(head_);
    head_.clear();
    return end + 4 - old;
}

void Framer::end_of_head(std::string_view head) {
    if (head.size() > kHeaderLimit) {
        set_fault("head too large");
        return;
    }
    Answer a;
    if (!parse_head(head, a)) {
        return;
    }
    answer_ = a;
    seen_ = 0;
    match_ = a.length == kBody.size();
    if (a.length == 0) {
        answer_.body_ok = false;  // the expected body is not empty
        state_ = State::Done;
    } else {
        state_ = State::Body;
    }
}

bool Framer::parse_head(std::string_view h, Answer& out) {
    // h ends with CRLF CRLF.
    if (h.size() < 16 || h.substr(0, 7) != "HTTP/1." || !is_digit(h[7]) || h[8] != ' ' || !is_digit(h[9]) ||
        !is_digit(h[10]) || !is_digit(h[11]) || (h[12] != ' ' && h[12] != '\r')) {
        set_fault("bad status line");
        return false;
    }
    out.status = (h[9] - '0') * 100 + (h[10] - '0') * 10 + (h[11] - '0');
    std::size_t pos = h.find("\r\n") + 2;
    bool have_length = false;
    std::uint64_t length = 0;
    while (pos < h.size() - 2) {  // the header lines; the last two bytes end the empty line
        const std::size_t eol = h.find("\r\n", pos);
        const std::string_view line = h.substr(pos, eol - pos);
        pos = eol + 2;
        const std::size_t colon = line.find(':');
        if (colon == std::string_view::npos || colon == 0) {
            set_fault("bad header line");
            return false;
        }
        const std::string_view name = line.substr(0, colon);
        const std::string_view value = trim(line.substr(colon + 1));
        if (iequals(name, "content-length")) {
            if (value.empty() || value.size() > kMaxLengthDigits) {
                set_fault("bad Content-Length");
                return false;
            }
            std::uint64_t v = 0;
            for (const char c : value) {
                if (!is_digit(c)) {
                    set_fault("bad Content-Length");
                    return false;
                }
                v = v * 10 + static_cast<std::uint64_t>(c - '0');
            }
            if (have_length && v != length) {
                set_fault("conflicting Content-Length");
                return false;
            }
            have_length = true;
            length = v;
        } else if (iequals(name, "transfer-encoding")) {
            set_fault("Transfer-Encoding");
            return false;
        } else if (iequals(name, "connection")) {
            if (has_close_token(value)) {
                out.close = true;
            }
        }
    }
    if (!have_length) {
        if (out.status / 100 != 1 && out.status != 204 && out.status != 304) {
            set_fault("no Content-Length");
            return false;
        }
        length = 0;
    }
    out.length = length;
    return true;
}

std::size_t Framer::feed_body(const char* p, std::size_t n) {
    const std::uint64_t left = answer_.length - seen_;
    const std::size_t take = n < left ? n : static_cast<std::size_t>(left);
    // match_ is only set when the length is kBody's, so seen_ + take never passes its end.
    if (match_ && std::memcmp(p, kBody.data() + seen_, take) != 0) {
        match_ = false;
    }
    seen_ += take;
    if (seen_ == answer_.length) {
        answer_.body_ok = match_;
        state_ = State::Done;
    }
    return take;
}

}  // namespace p2gen
