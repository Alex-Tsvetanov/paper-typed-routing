// capi-null, a null arm of design/review-runs/boundary-arms.md: the adapter of regexmatcher-v2-capi
// (arms/regexmatcher_v2_capi.cpp) around an empty function of the same C shape (arms/capi/null_capi.cpp, a
// translation unit of its own, compiled apart, no link-time optimisation). No router: the function reads
// the path's length and returns route 0 or 1, so the harness's 405 rule (which applies, as to
// regexmatcher-v2-capi) tests the answer and never falls back. Its time per lookup is the harness's loop,
// this adapter and one call across the C boundary: the null that regexmatcher-v2-capi's time is taken net
// of. As a null arm it has no agreement test and no probes.
#include <array>
#include <cstdint>
#include <string>

#include "arms/capi/v2_capi.h"
#include "core/runner.hpp"

namespace {

using namespace rb;

class CapiNullArm final {
public:
    static constexpr bool null_arm = true;

    static ArmInfo info() { return {"capi-null", "in-repo", "none", true}; }

    void add(const Route&, RouteId) {}
    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        std::array<std::uint32_t, 2 * kMaxParams> caps;
        std::uint32_t n = 0;
        const std::uint32_t id = rb_capi_null_at(arm_, static_cast<std::uint32_t>(m), path.data(), path.size(),
                                                 caps.data(), kMaxParams, &n);
        c.n = static_cast<std::uint8_t>(n);
        for (std::uint32_t i = 0; i < n; ++i) {
            c.v[i] = std::string_view(path).substr(caps[2 * i], caps[2 * i + 1]);
        }
        return id == 0xFFFF'FFFFu ? kNoRoute : id;
    }

private:
    const void* arm_ = this;  // a handle, as regexmatcher-v2-capi passes one; the function ignores it
};

}  // namespace

RB_ARM(CapiNullArm)
