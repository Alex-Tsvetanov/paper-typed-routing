// Round 2's rbench adapters as router arms of the server (design/round3/end-to-end.md, section 6):
// the C and C++ external routers, behind the server's one function pointer (route.hpp).
//
// Each adapter is compiled unchanged; shim/core/runner.hpp registers it here. The arm is built
// from the routes file as rbench builds it from a table: one rb::Route per line (rb::parse_route
// of the canonical text), route i as id i, finalize() once. A lookup hands the adapter the server's
// path string as it is (route.hpp: the server fills it once per request, for every arm). A miss gets
// round 2's harness rule for arms without a 405 of their own (bench/core/runner.hpp, full()): the
// same path under every other method that has routes.
#pragma once

#include <algorithm>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include "arms.hpp"
#include "core/arm.hpp"

namespace mserver {

using ExternalFactory = Arm (*)(const std::vector<RouteLine>& routes);

struct ExternalArm {
    std::string name;
    std::string version;
    ExternalFactory make;
};

// Called by RB_ARM at static initialization; returns true.
bool register_external(std::string name, std::string version, ExternalFactory make);

// The registered arms, in registration order.
const std::vector<ExternalArm>& external_arms();

namespace detail {

// The server numbers methods as RegexMatcher v2 does (route.hpp); rbench's seven are the first
// seven of them, in the same order.
static_assert(rb::kMethods == 7 && kGet == 0 && kPost == 1 && kPut == 2 && kDelete == 3 && kPatch == 4 &&
              kHead == 5 && kOptions == 6);

template <rb::Arm A>
struct External {
    A arm;
    rb::Captures caps;          // views into the arm's memory or into the path, until the next lookup
    std::uint16_t methods = 0;  // bit m for every method that has routes
};

// Round 2's harness runs every adapter's lookup through full(), which treats any id but kNoRoute as
// a route; an adapter with a 405 of its own (native_405) would answer kMethodNotAllowed instead,
// and none of the C and C++ adapters has one.
template <class A>
concept HasNative405 = requires { A::native_405; };

template <rb::Arm A>
rb::RouteId lookup(External<A>& e, unsigned method, const std::string& path) {
    return e.arm.lookup(static_cast<rb::Method>(method), path, e.caps);
}

template <rb::Arm A>
void find_external(const void* data, unsigned method, const std::string& path, RouteResult& out) {
    static_assert(!HasNative405<A>, "an adapter with its own 405 needs round 2's kMethodNotAllowed rule here");
    auto& e = *const_cast<External<A>*>(static_cast<const External<A>*>(data));  // the arm keeps results between calls
    out.allowed = 0;
    out.count = 0;
    const bool known = method < rb::kMethods;
    if (known) {
        const rb::RouteId id = lookup(e, method, path);
        if (id != rb::kNoRoute) {
            out.status = RouteStatus::Found;
            out.route = id;
            out.count = static_cast<std::uint8_t>(std::min<std::size_t>(e.caps.n, out.params.size()));
            for (std::uint8_t i = 0; i < out.count; ++i) {
                out.params[i] = matcher::route::Capture{e.caps.v[i].data(), e.caps.v[i].size()};
            }
            return;
        }
    }
    unsigned others = e.methods & ~(known ? 1u << method : 0u);
    for (unsigned m = 0; others != 0; ++m, others >>= 1) {
        if ((others & 1u) != 0 && lookup(e, m, path) != rb::kNoRoute) {
            out.allowed = static_cast<std::uint16_t>(out.allowed | (1u << m));
        }
    }
    out.status = out.allowed != 0 ? RouteStatus::MethodNotAllowed : RouteStatus::NotFound;
}

}  // namespace detail

// Builds arm A from exactly the file's routes (the server answers the probe GET / itself,
// Router::probe). Throws RefusedTable with the adapter's reason when it refuses them.
template <rb::Arm A>
Arm make_external(const std::vector<RouteLine>& routes) {
    auto e = std::make_shared<detail::External<A>>();
    try {
        for (std::size_t i = 0; i < routes.size(); ++i) {
            const auto m = static_cast<rb::Method>(routes[i].method);
            e->arm.add(rb::parse_route(m, routes[i].pattern), static_cast<rb::RouteId>(i));
            e->methods = static_cast<std::uint16_t>(e->methods | (1u << routes[i].method));
        }
        e->arm.finalize();
    } catch (const std::exception& ex) {
        throw RefusedTable(std::string(A::info().name) + " refused the routes: " + ex.what());
    }
    return {Router{detail::find_external<A>, e.get()}, e};
}

}  // namespace mserver
