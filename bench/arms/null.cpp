// The null arm: no router. Its lookup is one out-of-line call that reads the path's length
// and returns without matching, so the instructions and time it costs per lookup are those
// of the harness loop around a lookup (the ring access, the call, the sink), which the
// summaries subtract from every arm whose throughput loop is the harness's. It has no
// captures, so the sink's per-capture work (a few instructions per value) stays in the
// other arms' figures.
#include <string>

#include "core/runner.hpp"

namespace {

using namespace rb;

class NullArm final {
public:
    static constexpr bool native_405 = true;  // full() makes exactly one call
    static constexpr bool null_arm = true;

    static ArmInfo info() { return {"null", "in-repo", "none", true}; }

    void add(const Route&, RouteId) {}
    void finalize() {}

    [[gnu::noinline]] RouteId lookup(Method, const std::string& path, Captures& c) {
        c.n = 0;
        return static_cast<RouteId>(path.size() & 1u);
    }
};

}  // namespace

RB_ARM(NullArm)
