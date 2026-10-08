// The contract every arm meets, and the registry the driver selects arms from.
//
// An arm is a final class with
//     static ArmInfo info();
//     void add(const Route&, RouteId);   // throws Refused if it cannot hold the route
//     void finalize();                    // once, after the last add
//     RouteId lookup(Method, const std::string& path, Captures&);
// lookup returns kNoRoute on a miss. The captured values are views that stay valid until the
// arm's next lookup; an arm whose router returns owned strings keeps them in a member.
//
// The measurement code is a template over the arm type (core/runner.hpp), instantiated in the
// arm's own translation unit, so the timed loop calls lookup directly and never through a
// virtual function. Runner is the type-erased face the driver uses between measurements.
#pragma once

#include <concepts>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

#include "core/route.hpp"
#include "core/table.hpp"

namespace rb {

// Thrown by add() or finalize() when an arm cannot hold a table; the reason is recorded and
// the arm is reported absent for that table.
struct Refused : std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct ArmInfo {
    std::string name;
    std::string version;   // the pinned upstream version, or "in-repo"
    std::string captures;  // how captured values come back, for the record
    bool null = false;     // the null arm: no router, so no agreement test and no probes
};

template <class A>
concept Arm = std::is_final_v<A> && std::default_initializable<A> &&
              requires(A& a, const Route& r, RouteId id, Method m, const std::string& p, Captures& c) {
                  { A::info() } -> std::convertible_to<ArmInfo>;
                  { a.add(r, id) } -> std::same_as<void>;
                  { a.finalize() } -> std::same_as<void>;
                  { a.lookup(m, p, c) } -> std::same_as<RouteId>;
              };

struct MeasureOptions {
    int build_reps = 5;
    double verify_budget_s = 120.0;  // the agreement pass stops here (after 64 queries at least)
    double build_budget_s = 20.0;    // no further build repetitions once one took this long
    int epochs = 21;
    double pass_budget_s = 0.25;     // a timed pass over a slow arm's ring is cut to a prefix
    std::uint64_t latency_samples = 1 << 17;
    double latency_budget_s = 2.0;
    // The timed loops read the ring from its compact copy (the default), or, for the
    // disclosure of that choice, from the Query objects themselves (--ring-layout queries).
    bool ring_from_queries = false;
};

class Runner {
public:
    virtual ~Runner() = default;
    virtual ArmInfo describe() const = 0;
    // Builds the arm from the routes; throws Refused.
    virtual void build(const std::vector<Route>& routes) = 0;
    // One lookup through the arm's own function, for the probe and the agreement check.
    virtual RouteId lookup(Method m, const std::string& path, std::vector<std::string>& caps) = 0;
    // The whole measurement of one cell as a JSON object (core/runner.hpp).
    virtual std::string measure(const Table& t, const Ring& r, const MeasureOptions& o) = 0;
};

using Factory = std::unique_ptr<Runner> (*)();

struct Registered {
    std::string name;
    Factory make;
};

bool register_arm(std::string name, Factory make);
const std::vector<Registered>& registered_arms();

}  // namespace rb
