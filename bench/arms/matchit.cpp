// matchit (Rust crate; the router library axum builds on: axum 0.8.9 pins matchit 0.8.4, and this arm
// measures matchit's latest release), through a C interface (arms/rust/matchit_arm.rs),
// one router per method. A parameter is {name} and a catch-all {*name}, the canonical syntax
// of this harness. Captured values come back as offsets into the query path, so they are
// views and nothing is copied; each lookup is one call across the C boundary.
#include <array>
#include <cstdint>
#include <string>

#include "core/runner.hpp"
#include "matchit_sources.h"  // the digest of the Rust crate (cmake/ffi-rust.cmake)

static_assert(sizeof(RB_FFI_SOURCES) > 1);

extern "C" {
struct RbMatchit;
RbMatchit* rb_matchit_new(std::uint32_t methods);
void rb_matchit_free(RbMatchit* arm);
int rb_matchit_insert(RbMatchit* arm, std::uint32_t method, const char* pattern, std::size_t len, std::uint32_t id,
                      char* err, std::size_t errcap);
std::uint32_t rb_matchit_at(const RbMatchit* arm, std::uint32_t method, const char* path, std::size_t len,
                            std::uint32_t* caps, std::uint32_t max, std::uint32_t* ncaps);
}

namespace {

using namespace rb;

class MatchitArm final {
public:
    static ArmInfo info() { return {"matchit", "ibraheemdev/matchit 0.9.2 (Rust, C interface)", "views into the path"}; }

    MatchitArm() : arm_(rb_matchit_new(kMethods)) {}
    ~MatchitArm() { rb_matchit_free(arm_); }
    MatchitArm(const MatchitArm&) = delete;
    MatchitArm& operator=(const MatchitArm&) = delete;

    void add(const Route& r, RouteId id) {
        const std::string pattern = render(r);
        std::array<char, 512> err{};
        if (rb_matchit_insert(arm_, static_cast<std::uint32_t>(r.method), pattern.data(), pattern.size(), id,
                              err.data(), err.size()) != 0) {
            throw Refused(std::string("matchit: ") + err.data());
        }
    }

    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        std::array<std::uint32_t, 2 * kMaxParams> caps;
        std::uint32_t n = 0;
        const std::uint32_t id = rb_matchit_at(arm_, static_cast<std::uint32_t>(m), path.data(), path.size(),
                                               caps.data(), kMaxParams, &n);
        c.n = static_cast<std::uint8_t>(n);
        for (std::uint32_t i = 0; i < n; ++i) {
            c.v[i] = std::string_view(path).substr(caps[2 * i], caps[2 * i + 1]);
        }
        return id == 0xFFFF'FFFFu ? kNoRoute : id;
    }

private:
    RbMatchit* arm_;
};

}  // namespace

RB_ARM(MatchitArm)
