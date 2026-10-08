// actix-router (Rust crate, the router of actix-web), through a C interface
// (arms/rust/actix_router_arm.rs), one Router per method, built with the crate's default
// features. A parameter is {name} (the regex [^/]+) and a catch-all is the tail segment
// {name}* (the regex .*). The Router tries its routes in registration order and the first
// that matches wins; there is no precedence of a literal over a parameter.
//
// actix-web matches the path to a resource first and picks one of the resource's routes by
// its method guard, answering 405 itself when none fits. This arm keeps one Router per method
// instead, so that the method is chosen before the path is matched, as in the other arms; a
// lookup does not tell 404 from 405 and the harness's rule applies (not native_405).
//
// A lookup matches a Path over the query path as &str, so nothing is percent-decoded, and the
// captured values come back as offsets into the query path: they are views and nothing is
// copied. Each lookup is one call across the C boundary.
//
// ResourceDef::new panics on a pattern it cannot parse, and the crate is built with panic =
// "abort", so add() refuses a route whose pattern it would not take: a parameter name that
// is not an identifier (regex capture names), a name repeated in the route, more than 16
// parameters, or a literal with '{', '}' or a trailing '*'.
#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include "core/runner.hpp"
#include "actix_router_sources.h"  // the digest of the Rust crate (cmake/ffi-rust.cmake)

static_assert(sizeof(RB_FFI_SOURCES) > 1);

// ResourceDef::parse leaks the pattern strings it builds on purpose, to keep them for the
// life of the process (actix-router 0.5.4, src/resource.rs, documented there). Under ASan,
// LeakSanitizer ignores a leak whose allocation stack has the frame
// <actix_router::resource::ResourceDef>::parse, and no other: a leak from any other function
// of the crate, or from this adapter, is still reported.
#if defined(__has_feature)
#if __has_feature(address_sanitizer)
extern "C" const char* __lsan_default_suppressions() {
    return "leak:actix_router::resource::ResourceDef>::parse\n";
}
#endif
#endif

extern "C" {
struct RbActix;
RbActix* rb_actix_new(std::uint32_t methods);
void rb_actix_free(RbActix* arm);
int rb_actix_insert(RbActix* arm, std::uint32_t method, const char* pattern, std::size_t len, std::uint32_t id,
                    char* err, std::size_t errcap);
void rb_actix_finalize(RbActix* arm);
std::uint32_t rb_actix_at(RbActix* arm, std::uint32_t method, const char* path, std::size_t len, std::uint32_t* caps,
                          std::uint32_t max, std::uint32_t* ncaps);
}

namespace {

using namespace rb;

constexpr std::size_t kActixMaxDynamic = 16;  // MAX_DYNAMIC_SEGMENTS in actix-router's resource.rs

bool identifier(const std::string& s) {
    if (s.empty() || (s[0] >= '0' && s[0] <= '9')) {
        return false;
    }
    for (const char ch : s) {
        const bool ok = (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9') || ch == '_';
        if (!ok) {
            return false;
        }
    }
    return true;
}

// Why ResourceDef::new would panic on the route's pattern, or an empty string.
std::string unparsable(const Route& r) {
    std::vector<std::string> names;
    for (std::size_t i = 0; i < r.segs.size(); ++i) {
        const Segment& s = r.segs[i];
        if (s.kind == Seg::Literal) {
            if (s.text.find_first_of("{}") != std::string::npos ||
                (i + 1 == r.segs.size() && !s.text.empty() && s.text.back() == '*')) {
                return "literal '" + s.text + "' would be read as pattern syntax";
            }
            continue;
        }
        if (!identifier(s.text)) {
            return "parameter name '" + s.text + "' is not a regex capture name";
        }
        for (const auto& n : names) {
            if (n == s.text) {
                return "parameter name '" + s.text + "' repeats";
            }
        }
        names.push_back(s.text);
    }
    if (names.size() > kActixMaxDynamic) {
        return "more than 16 parameters";
    }
    return {};
}

class ActixRouterArm final {
public:
    static ArmInfo info() { return {"actix-router", "actix-router 0.5.4 (Rust, C interface)", "views into the path"}; }

    ActixRouterArm() : arm_(rb_actix_new(kMethods)) {}
    ~ActixRouterArm() { rb_actix_free(arm_); }
    ActixRouterArm(const ActixRouterArm&) = delete;
    ActixRouterArm& operator=(const ActixRouterArm&) = delete;

    void add(const Route& r, RouteId id) {
        if (const std::string why = unparsable(r); !why.empty()) {
            throw Refused("actix-router: " + why);
        }
        std::string pattern;
        for (const Segment& s : r.segs) {
            pattern += '/';
            if (s.kind == Seg::Literal) {
                pattern += s.text;
            } else {
                pattern += '{' + s.text + (s.kind == Seg::Rest ? "}*" : "}");
            }
        }
        std::array<char, 512> err{};
        if (rb_actix_insert(arm_, static_cast<std::uint32_t>(r.method), pattern.data(), pattern.size(), id, err.data(),
                            err.size()) != 0) {
            throw Refused(std::string("actix-router: ") + err.data());
        }
    }

    void finalize() { rb_actix_finalize(arm_); }

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        std::array<std::uint32_t, 2 * kMaxParams> caps;
        std::uint32_t n = 0;
        const std::uint32_t id = rb_actix_at(arm_, static_cast<std::uint32_t>(m), path.data(), path.size(), caps.data(),
                                             kMaxParams, &n);
        c.n = static_cast<std::uint8_t>(n);
        for (std::uint32_t i = 0; i < n; ++i) {
            c.v[i] = std::string_view(path).substr(caps[2 * i], caps[2 * i + 1]);
        }
        return id == 0xFFFF'FFFFu ? kNoRoute : id;
    }

private:
    RbActix* arm_;
};

}  // namespace

RB_ARM(ActixRouterArm)
