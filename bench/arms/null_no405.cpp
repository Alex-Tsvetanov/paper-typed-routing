// The second null arm: the null arm's lookup (one out-of-line call that reads the path's length
// and returns without matching), without a 405 of its own, so the harness applies its 405 rule
// to it (core/runner.hpp, full()): the test of the answer against "no route" on every lookup, the
// fallback itself never taken (the answer is route 0 or 1). It is the loop null of every arm whose
// lookups the harness calls and that has no 405 of its own (loop_null "null-no405"), so that H2's
// net counts take the harness's 405 test out of those arms as they take it out of v2, which has
// its own 405 and is paired with the null arm.
#include <string>

#include "core/runner.hpp"

namespace {

using namespace rb;

class NullNo405Arm final {
public:
    static constexpr bool null_arm = true;

    static ArmInfo info() { return {"null-no405", "in-repo", "none", true}; }

    void add(const Route&, RouteId) {}
    void finalize() {}

    [[gnu::noinline]] RouteId lookup(Method, const std::string& path, Captures& c) {
        c.n = 0;
        return static_cast<RouteId>(path.size() & 1u);
    }
};

}  // namespace

RB_ARM(NullNo405Arm)
