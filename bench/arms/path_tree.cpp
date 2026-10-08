// path-tree 0.8.3 (Rust crate, viz-rs/path-tree), through a C interface
// (arms/rust/path_tree_arm.rs), one tree per method. A parameter is :name and a catch-all
// :name+ (one or more segments). Captured values come back as offsets into the query path, so
// they are views and nothing is copied; each lookup is one call across the C boundary.
// path-tree has no 405 of its own: the harness's rule applies.
#include <array>
#include <cstdint>
#include <string>

#include "core/runner.hpp"
#include "path_tree_sources.h"  // the digest of the Rust crate (cmake/ffi-rust.cmake)

static_assert(sizeof(RB_FFI_SOURCES) > 1);

extern "C" {
struct RbPathTree;
RbPathTree* rb_path_tree_new(std::uint32_t methods);
void rb_path_tree_free(RbPathTree* arm);
int rb_path_tree_insert(RbPathTree* arm, std::uint32_t method, const char* pattern, std::size_t len, std::uint32_t id);
std::uint32_t rb_path_tree_find(const RbPathTree* arm, std::uint32_t method, const char* path, std::size_t len,
                                std::uint32_t* caps, std::uint32_t max, std::uint32_t* ncaps);
}

namespace {

using namespace rb;

class PathTreeArm final {
public:
    static ArmInfo info() { return {"path-tree", "viz-rs/path-tree 0.8.3 (Rust, C interface)", "views into the path"}; }

    PathTreeArm() : arm_(rb_path_tree_new(kMethods)) {}
    ~PathTreeArm() { rb_path_tree_free(arm_); }
    PathTreeArm(const PathTreeArm&) = delete;
    PathTreeArm& operator=(const PathTreeArm&) = delete;

    void add(const Route& r, RouteId id) {
        std::string pattern;
        for (const Segment& s : r.segs) {
            pattern += '/';
            pattern += s.kind == Seg::Literal ? s.text : ":" + s.text + (s.kind == Seg::Rest ? "+" : "");
        }
        if (rb_path_tree_insert(arm_, static_cast<std::uint32_t>(r.method), pattern.data(), pattern.size(), id) != 0) {
            throw Refused("path-tree: the pattern is not UTF-8");
        }
    }

    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        std::array<std::uint32_t, 2 * kMaxParams> caps;
        std::uint32_t n = 0;
        const std::uint32_t id = rb_path_tree_find(arm_, static_cast<std::uint32_t>(m), path.data(), path.size(),
                                               caps.data(), kMaxParams, &n);
        c.n = static_cast<std::uint8_t>(n);
        for (std::uint32_t i = 0; i < n; ++i) {
            c.v[i] = std::string_view(path).substr(caps[2 * i], caps[2 * i + 1]);
        }
        return id == 0xFFFF'FFFFu ? kNoRoute : id;
    }

private:
    RbPathTree* arm_;
};

}  // namespace

RB_ARM(PathTreeArm)
