// HTTP/1.1 for the paper's minimal server (design/round2/minimal-server.md): parsing one request
// from a connection's buffer, and the responses, whose bytes are built once and copied. No I/O
// and no router here; route.hpp is the router interface.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

#include "route.hpp"

namespace mserver {

inline constexpr std::size_t kMaxHead = 8192;  // a request head longer than this is refused (431)

struct Request {
    unsigned method = kOtherMethod;  // kGet ... kTrace, or kOtherMethod
    std::string_view target;         // the request target as sent
    std::string_view path;           // the target up to its query
    int minor = 1;                   // HTTP/1.minor
    bool keep_alive = true;          // after this request's response
};

enum class Parse : std::uint8_t {
    Complete,    // a whole request: its head, and its body (Content-Length bytes), which is skipped
    Incomplete,  // more bytes are needed
    Refused      // answer `refusal`, then close the connection
};

struct Parsed {
    Parse state = Parse::Incomplete;
    std::size_t consumed = 0;  // with Complete: the bytes of the head and the body
    unsigned refusal = 0;      // with Refused: 400, 431 or 501
    Request request;
};

// The first request in buf, which starts at a request's first byte. The views of the request
// point into buf.
Parsed parse_request(std::string_view buf) noexcept;

// The server's responses. The fixed ones are built at start; the Date field of every one is
// patched in place (set_date), once a second.
class Responses {
public:
    Responses();

    // An IMF-fixdate of 29 bytes ("Sun, 06 Nov 1994 08:49:37 GMT").
    void set_date(std::string_view date) noexcept;

    // The answer to a request, appended to out: the router's result, HEAD answered by a GET
    // route when no HEAD route matches, 405 with Allow, 404.
    void answer(const Request& req, const Router& router, RouteResult& scratch, std::string& out) const;

    // A refusal (400, 413, 431, 501), with Connection: close.
    void refuse(unsigned status, std::string& out) const;

private:
    enum Kind : std::uint8_t { kOk, kNotFound, kKinds };
    // Per kind and connection disposition: the whole response, and where its header section
    // ends (a HEAD response is that prefix).
    struct Fixed {
        std::string bytes;
        std::size_t head_end = 0;
        std::size_t date_at = 0;
    };
    enum Conn : std::uint8_t { kKeep11, kClose, kKeep10, kConns };
    std::array<std::array<Fixed, kConns>, kKinds> fixed_;
    std::array<Fixed, 4> refusals_;  // 400, 413, 431, 501
    std::string date_;

    static Conn conn_of(const Request& req) noexcept;
    void method_not_allowed(const Request& req, std::uint16_t allowed, std::string& out) const;
};

}  // namespace mserver
