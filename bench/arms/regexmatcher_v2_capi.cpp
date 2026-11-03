// regexmatcher-v2-capi, a boundary arm of design/review-runs/boundary-arms.md: RegexMatcher v2 behind its own
// C interface (arms/capi/v2_capi.h), defined in a translation unit of its own (arms/capi/v2_capi.cpp) that
// is compiled apart from this adapter, without link-time optimisation. The adapter has the shape of the
// Rust arms' adapters (arms/matchit.cpp): one call across the C interface per lookup, the captured values
// back as offsets into the query path, and the harness's 405 rule (not native_405), as for the Rust arms.
// It is the symmetric arm of the Rust arms: v2 behind the same kind of call, in the same direction.
// Exploratory: it decides nothing.
#include <array>
#include <cstdint>
#include <new>
#include <string>

#include "arms/capi/v2_capi.h"
#include "core/runner.hpp"

#ifndef RB_REGEXMATCHER_COMMIT
#define RB_REGEXMATCHER_COMMIT "unknown"
#endif

namespace {

using namespace rb;

class V2CapiArm final {
public:
    static ArmInfo info() {
        return {"regexmatcher-v2-capi",
                std::string("RegexMatcher v2 ") + std::string(RB_REGEXMATCHER_COMMIT).substr(0, 9) +
                    " (table built at run time) behind an extern \"C\" interface",
                "views into the path"};
    }

    V2CapiArm() : arm_(rb_v2capi_new()) {
        if (arm_ == nullptr) {
            throw std::bad_alloc();
        }
    }
    ~V2CapiArm() { rb_v2capi_free(arm_); }
    V2CapiArm(const V2CapiArm&) = delete;
    V2CapiArm& operator=(const V2CapiArm&) = delete;

    void add(const Route& r, RouteId id) {
        const std::string pattern = render(r);
        std::array<char, 512> err{};
        if (rb_v2capi_insert(arm_, static_cast<std::uint32_t>(r.method), pattern.data(), pattern.size(), id,
                             err.data(), err.size()) != 0) {
            throw Refused(std::string("regexmatcher-v2-capi: ") + err.data());
        }
    }

    void finalize() {
        std::array<char, 512> err{};
        if (rb_v2capi_finalize(arm_, err.data(), err.size()) != 0) {
            throw Refused(std::string("regexmatcher-v2-capi: ") + err.data());
        }
    }

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        std::array<std::uint32_t, 2 * kMaxParams> caps;
        std::uint32_t n = 0;
        const std::uint32_t id = rb_v2capi_at(arm_, static_cast<std::uint32_t>(m), path.data(), path.size(),
                                              caps.data(), kMaxParams, &n);
        c.n = static_cast<std::uint8_t>(n);
        for (std::uint32_t i = 0; i < n; ++i) {
            c.v[i] = std::string_view(path).substr(caps[2 * i], caps[2 * i + 1]);
        }
        return id == 0xFFFF'FFFFu ? kNoRoute : id;
    }

private:
    RbV2Capi* arm_;
};

}  // namespace

RB_ARM(V2CapiArm)
