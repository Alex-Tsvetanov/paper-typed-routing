// The router interface of the paper's minimal server (design/round2/minimal-server.md, section 2):
// one function pointer, so that the server's own machine code is the same for every router arm.
// A lookup's result is RegexMatcher v2's Match, reused from one request to the next: the v2 arm
// fills it with find_into, and the other arms set the same fields.
#pragma once

#include <cstdint>
#include <string>
#include <string_view>

#include <matcher/route/lookup.hpp>

// The instruction set of this build (bench/cmake/isa.cmake), a compiled input of every target.
#include "rb_isa.h"

namespace mserver {

// Methods as RegexMatcher v2's route matcher numbers them.
inline constexpr unsigned kGet = 0;
inline constexpr unsigned kPost = 1;
inline constexpr unsigned kPut = 2;
inline constexpr unsigned kDelete = 3;
inline constexpr unsigned kPatch = 4;
inline constexpr unsigned kHead = 5;
inline constexpr unsigned kOptions = 6;
inline constexpr unsigned kConnect = 7;
inline constexpr unsigned kTrace = 8;
inline constexpr unsigned kMethods = 9;
inline constexpr unsigned kOtherMethod = 9;  // a method token the server does not know

// status, count (captured values), allowed (with MethodNotAllowed: bit m for every method that
// matches), route, and the captured values, of which only the first `count` are ever written.
using RouteResult = matcher::route::Match;
using RouteStatus = matcher::route::Status;

// The path comes as one std::string that the server fills once per request, for every arm (v2 and
// null included): round 2's adapters take the path as const std::string&, so every arm's lookup then
// starts from the same bytes, and no arm pays a copy the others do not.
using FindFn = void (*)(const void* router, unsigned method, const std::string& path, RouteResult& out);

// The route id of lab/t1's readiness probe, GET /, which the server answers itself without asking
// the router (design/round3/end-to-end.md, section 5), so that every router holds exactly the routes
// of its table; kNoProbe when the routes file has a route for "/" (the router answers it then).
inline constexpr std::uint32_t kNoProbe = 0xFFFF'FFFFu;

struct Router {
    FindFn find = nullptr;
    const void* data = nullptr;
    std::uint32_t probe = kNoProbe;

    void operator()(unsigned method, const std::string& path, RouteResult& out) const {
        if (probe != kNoProbe && path.size() == 1 && path[0] == '/') {
            const bool get = method == kGet || method == kHead;
            out.status = get ? RouteStatus::Found : RouteStatus::MethodNotAllowed;
            out.allowed = get ? 0 : static_cast<std::uint16_t>(1u << kGet);
            out.route = probe;
            out.count = 0;
            return;
        }
        find(data, method, path, out);
    }
};

}  // namespace mserver
