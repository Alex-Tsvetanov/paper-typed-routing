// rust-null, a null arm of design/review-runs/boundary-arms.md: the adapter of the Rust arms (arms/matchit.cpp)
// around an empty Rust function of the same C shape (arms/rust/rust_null_arm.rs, in the Rust arms' one static
// library). No router: the function reads the path's length and returns route 0 or 1, so the harness's 405
// rule (which applies, as to the Rust arms) tests the answer and never falls back. Its time per lookup is the
// harness's loop, this adapter and one call across the Rust boundary: the null that the Rust arms' times are
// taken net of. As a null arm it has no agreement test and no probes.
#include <array>
#include <cstdint>
#include <string>

#include "core/runner.hpp"
#include "rust_null_sources.h"  // the digest of the Rust crate (cmake/ffi-rust.cmake)

static_assert(sizeof(RB_FFI_SOURCES) > 1);

extern "C" {
std::uint32_t rb_rust_null_at(const void* arm, std::uint32_t method, const char* path, std::size_t len,
                              std::uint32_t* caps, std::uint32_t max, std::uint32_t* ncaps);
}

namespace {

using namespace rb;

class RustNullArm final {
public:
    static constexpr bool null_arm = true;

    static ArmInfo info() { return {"rust-null", "in-repo (Rust, C interface)", "none", true}; }

    void add(const Route&, RouteId) {}
    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        std::array<std::uint32_t, 2 * kMaxParams> caps;
        std::uint32_t n = 0;
        const std::uint32_t id = rb_rust_null_at(arm_, static_cast<std::uint32_t>(m), path.data(), path.size(),
                                                 caps.data(), kMaxParams, &n);
        c.n = static_cast<std::uint8_t>(n);
        for (std::uint32_t i = 0; i < n; ++i) {
            c.v[i] = std::string_view(path).substr(caps[2 * i], caps[2 * i + 1]);
        }
        return id == 0xFFFF'FFFFu ? kNoRoute : id;
    }

private:
    const void* arm_ = this;  // a handle, as the Rust arms pass one; the function ignores it
};

}  // namespace

RB_ARM(RustNullArm)
