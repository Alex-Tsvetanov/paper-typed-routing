// The router interface of the paper's minimal server (design/round2/minimal-server.md, section 2):
// one function pointer, so that the server's own machine code is the same for every router arm.
// A lookup's result is RegexMatcher v2's Match, reused from one request to the next: the v2 arm
// fills it with find_into, and the other arms set the same fields.
#pragma once

#include <cstdint>
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

using FindFn = void (*)(const void* router, unsigned method, std::string_view path, RouteResult& out);

struct Router {
    FindFn find = nullptr;
    const void* data = nullptr;

    void operator()(unsigned method, std::string_view path, RouteResult& out) const { find(data, method, path, out); }
};

}  // namespace mserver
