// HTTP/1.1 for the paper's minimal server: see http1.hpp.
#include "http1.hpp"

#include <algorithm>
#include <cstring>

namespace mserver {

namespace {

constexpr std::string_view kBody = "Hello, World!";
constexpr std::size_t kDateLen = 29;  // an IMF-fixdate
constexpr std::string_view kInitialDate = "Thu, 01 Jan 1970 00:00:00 GMT";

bool is_tchar(char c) noexcept {
    if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) {
        return true;
    }
    return std::string_view("!#$%&'*+-.^_`|~").find(c) != std::string_view::npos;
}

bool is_token(std::string_view s) noexcept {
    return !s.empty() && std::all_of(s.begin(), s.end(), is_tchar);
}

char lower(char c) noexcept {
    return c >= 'A' && c <= 'Z' ? static_cast<char>(c - 'A' + 'a') : c;
}

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

// Whether a comma-separated list of tokens holds `token` (case-insensitive).
bool has_token(std::string_view list, std::string_view token) noexcept {
    while (!list.empty()) {
        const std::size_t comma = list.find(',');
        if (iequals(trim(list.substr(0, comma)), token)) {
            return true;
        }
        if (comma == std::string_view::npos) {
            break;
        }
        list.remove_prefix(comma + 1);
    }
    return false;
}

unsigned method_of(std::string_view m) noexcept {
    constexpr std::string_view names[kMethods] = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "CONNECT", "TRACE"};
    for (unsigned i = 0; i < kMethods; ++i) {
        if (m == names[i]) {
            return i;
        }
    }
    return kOtherMethod;
}

Parsed refused(unsigned status) noexcept {
    Parsed p;
    p.state = Parse::Refused;
    p.refusal = status;
    return p;
}

}  // namespace

Parsed parse_request(std::string_view buf) noexcept {
    // The head ends with an empty line, within kMaxHead bytes.
    const std::size_t end = buf.substr(0, std::min(buf.size(), kMaxHead)).find("\r\n\r\n");
    if (end == std::string_view::npos) {
        return buf.size() >= kMaxHead ? refused(431) : Parsed{};
    }
    const std::size_t head_end = end + 4;
    std::string_view head = buf.substr(0, end + 2);  // every line with its CRLF

    // The request line: method SP request-target SP HTTP-version.
    const std::size_t eol = head.find("\r\n");
    const std::string_view line = head.substr(0, eol);
    head.remove_prefix(eol + 2);
    const std::size_t sp1 = line.find(' ');
    const std::size_t sp2 = sp1 == std::string_view::npos ? sp1 : line.find(' ', sp1 + 1);
    if (sp2 == std::string_view::npos) {
        return refused(400);
    }
    const std::string_view method = line.substr(0, sp1);
    const std::string_view target = line.substr(sp1 + 1, sp2 - sp1 - 1);
    const std::string_view version = line.substr(sp2 + 1);
    if (!is_token(method) || target.empty() || target.front() != '/' || version.size() != 8 ||
        version.substr(0, 7) != "HTTP/1." || version[7] < '0' || version[7] > '9') {
        return refused(400);
    }
    for (const char c : target) {
        if (static_cast<unsigned char>(c) <= 0x20 || c == 0x7F) {
            return refused(400);
        }
    }

    // The header fields.
    bool has_length = false;
    std::size_t length = 0;
    bool close = false;
    bool keep = false;
    while (!head.empty()) {
        const std::size_t e = head.find("\r\n");
        const std::string_view field = head.substr(0, e);
        head.remove_prefix(e + 2);
        const std::size_t colon = field.find(':');
        if (colon == std::string_view::npos || !is_token(field.substr(0, colon))) {
            return refused(400);  // no name, a bad name, or an obsolete line folding
        }
        const std::string_view name = field.substr(0, colon);
        const std::string_view value = trim(field.substr(colon + 1));
        if (iequals(name, "content-length")) {
            if (value.empty() || value.size() > 12 ||
                !std::all_of(value.begin(), value.end(), [](char c) { return c >= '0' && c <= '9'; })) {
                return refused(400);
            }
            std::size_t n = 0;
            for (const char c : value) {
                n = n * 10 + static_cast<std::size_t>(c - '0');
            }
            if (has_length && n != length) {
                return refused(400);
            }
            has_length = true;
            length = n;
        } else if (iequals(name, "transfer-encoding")) {
            return refused(501);
        } else if (iequals(name, "connection")) {
            close = close || has_token(value, "close");
            keep = keep || has_token(value, "keep-alive");
        }
    }

    const unsigned m = method_of(method);
    if (m == kOtherMethod) {
        return refused(501);
    }
    if (buf.size() - head_end < length) {
        return Parsed{};  // the body has not all arrived
    }
    Parsed p;
    p.state = Parse::Complete;
    p.consumed = head_end + length;
    p.request.method = m;
    p.request.target = target;
    p.request.path = target.substr(0, target.find('?'));
    p.request.minor = version[7] - '0';
    p.request.keep_alive = p.request.minor >= 1 ? !close : (keep && !close);
    return p;
}

namespace {
volatile std::uint64_t g_sink = 0;  // the last server's sink (Responses::~Responses)
}  // namespace

Responses::~Responses() { g_sink = sink_; }

Responses::Responses(bool check) : date_(kInitialDate), check_(check) {
    const std::string_view conn_line[kConns] = {"", "Connection: close\r\n", "Connection: keep-alive\r\n"};
    for (std::size_t c = 0; c < kConns; ++c) {
        Fixed& ok = fixed_[kOk][c];
        ok.bytes = "HTTP/1.1 200 OK\r\nDate: ";
        ok.date_at = ok.bytes.size();
        ok.bytes.append(date_).append("\r\nContent-Type: text/plain\r\nContent-Length: 13\r\n").append(conn_line[c]).append("\r\n");
        ok.head_end = ok.bytes.size();
        ok.bytes.append(kBody);
        Fixed& nf = fixed_[kNotFound][c];
        nf.bytes = "HTTP/1.1 404 Not Found\r\nDate: ";
        nf.date_at = nf.bytes.size();
        nf.bytes.append(date_).append("\r\nContent-Length: 0\r\n").append(conn_line[c]).append("\r\n");
        nf.head_end = nf.bytes.size();
    }
    const std::pair<unsigned, std::string_view> refusals[4] = {
        {400, "Bad Request"}, {413, "Content Too Large"}, {431, "Request Header Fields Too Large"}, {501, "Not Implemented"}};
    for (std::size_t i = 0; i < 4; ++i) {
        Fixed& f = refusals_[i];
        f.bytes = "HTTP/1.1 " + std::to_string(refusals[i].first) + " " + std::string(refusals[i].second) + "\r\nDate: ";
        f.date_at = f.bytes.size();
        f.bytes.append(date_).append("\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
        f.head_end = f.bytes.size();
    }
}

void Responses::set_date(std::string_view date) noexcept {
    if (date.size() != kDateLen) {
        return;
    }
    date_.replace(0, kDateLen, date);
    for (auto& kind : fixed_) {
        for (Fixed& f : kind) {
            std::memcpy(f.bytes.data() + f.date_at, date.data(), kDateLen);
        }
    }
    for (Fixed& f : refusals_) {
        std::memcpy(f.bytes.data() + f.date_at, date.data(), kDateLen);
    }
}

Responses::Conn Responses::conn_of(const Request& req) noexcept {
    if (!req.keep_alive) {
        return kClose;
    }
    return req.minor >= 1 ? kKeep11 : kKeep10;
}

void Responses::answer(const Request& req, const Router& router, RouteResult& scratch, std::string& out) const {
    const bool head = req.method == kHead;
    const Conn c = conn_of(req);
    path_.assign(req.path.data(), req.path.size());
    router(req.method, path_, scratch);
    if (scratch.status == RouteStatus::MethodNotAllowed && head && (scratch.allowed & (1u << kGet)) != 0) {
        // HEAD with no HEAD route: the GET route answers, without content.
        const std::uint16_t allowed = scratch.allowed;
        router(kGet, path_, scratch);
        if (scratch.status != RouteStatus::Found) {
            method_not_allowed(req, allowed, out);
            return;
        }
    }
    switch (scratch.status) {
        case RouteStatus::Found: {
            if (check_) {
                found_check(req, scratch, out);
                return;
            }
            std::uint64_t s = scratch.route;
            for (std::uint8_t i = 0; i < scratch.count; ++i) {
                const std::size_t n = scratch.params[i].size();
                s += n + (n == 0 ? 0u : static_cast<unsigned char>(scratch.params[i].data()[0]));
            }
            sink_ += s;
            const Fixed& f = fixed_[kOk][c];
            out.append(f.bytes, 0, head ? f.head_end : f.bytes.size());
            return;
        }
        case RouteStatus::MethodNotAllowed:
            method_not_allowed(req, scratch.allowed, out);
            return;
        case RouteStatus::NotFound:
            out.append(fixed_[kNotFound][c].bytes);
            return;
    }
}

void Responses::method_not_allowed(const Request& req, std::uint16_t allowed, std::string& out) const {
    constexpr unsigned order[kMethods] = {kGet, kHead, kPost, kPut, kDelete, kPatch, kOptions, kConnect, kTrace};
    constexpr std::string_view names[kMethods] = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "CONNECT", "TRACE"};
    if ((allowed & (1u << kGet)) != 0) {
        allowed = static_cast<std::uint16_t>(allowed | (1u << kHead));
    }
    out.append("HTTP/1.1 405 Method Not Allowed\r\nDate: ").append(date_).append("\r\nContent-Length: 0\r\nAllow: ");
    bool first = true;
    for (const unsigned m : order) {
        if ((allowed & (1u << m)) != 0) {
            if (!first) {
                out.append(", ");
            }
            out.append(names[m]);
            first = false;
        }
    }
    out.append("\r\n");
    switch (conn_of(req)) {
        case kClose: out.append("Connection: close\r\n"); break;
        case kKeep10: out.append("Connection: keep-alive\r\n"); break;
        default: break;
    }
    out.append("\r\n");
}

void Responses::refuse(unsigned status, std::string& out) const {
    const std::size_t i = status == 413 ? 1 : status == 431 ? 2 : status == 501 ? 3 : 0;
    out.append(refusals_[i].bytes);
}

void Responses::found_check(const Request& req, const RouteResult& found, std::string& out) const {
    std::string body = std::to_string(found.route);
    for (std::uint8_t i = 0; i < found.count; ++i) {
        body += '\t';
        body.append(found.params[i].data(), found.params[i].size());
    }
    body += '\n';
    out.append("HTTP/1.1 200 OK\r\nDate: ").append(date_).append("\r\nContent-Type: text/plain\r\nContent-Length: ");
    out.append(std::to_string(body.size())).append("\r\n");
    switch (conn_of(req)) {
        case kClose: out.append("Connection: close\r\n"); break;
        case kKeep10: out.append("Connection: keep-alive\r\n"); break;
        default: break;
    }
    out.append("\r\n");
    if (req.method != kHead) {
        out.append(body);
    }
}

std::size_t answer_all(std::string_view in, bool full, const Responses& responses, const Router& router,
                       RouteResult& scratch, std::string& out, bool& closing) {
    std::size_t off = 0;
    while (!closing && off < in.size()) {
        const Parsed p = parse_request(in.substr(off));
        if (p.state == Parse::Complete) {
            responses.answer(p.request, router, scratch, out);
            off += p.consumed;
            closing = !p.request.keep_alive;
        } else if (p.state == Parse::Refused) {
            responses.refuse(p.refusal, out);
            closing = true;
        } else {
            if (off == 0 && full) {
                responses.refuse(413, out);  // a request larger than the buffer
                closing = true;
            }
            break;
        }
    }
    return off;
}

}  // namespace mserver
