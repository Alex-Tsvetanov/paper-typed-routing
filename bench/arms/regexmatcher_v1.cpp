// RegexMatcher v1, the regex-set engine at commit d16f30a8, behind the pattern-to-regex wrapper
// (arms/regexmatcher_v1_wrap.hpp): a reference arm, not a competitor. The wrapper is the one the
// paper's server uses for its v1 router arm, the reference of H6.
#include "arms/regexmatcher_v1_wrap.hpp"

#include "core/runner.hpp"

namespace {

using namespace rb;

class RegexMatcherV1Arm final {
public:
    static ArmInfo info() {
        return {"regexmatcher-v1", "cpp-for-everything/RegexMatcher d16f30a8 (the regex-set engine, v1)",
                "views into the path"};
    }

    void add(const Route& r, RouteId id) {
        std::vector<Seg1> segs;
        for (const Segment& s : r.segs) {
            segs.push_back({s.kind == Seg::Literal ? rm_v1::SegKind::Literal
                                                   : (s.kind == Seg::Param ? rm_v1::SegKind::Param : rm_v1::SegKind::Rest),
                            s.text});
        }
        router_.add(static_cast<std::size_t>(r.method), rm_v1::pattern_regex(segs), id);
    }

    void finalize() { router_.compile(); }

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        const rm_v1::Result r = router_.match(static_cast<std::size_t>(m), path);
        c.n = 0;
        for (std::size_t i = 0; i < r.count && c.n < kMaxParams; ++i) {
            c.v[c.n++] = r.values[i];
        }
        return r.route == 0xFFFF'FFFFu ? kNoRoute : r.route;
    }

private:
    struct Seg1 {
        rm_v1::SegKind kind;
        std::string_view text;
    };
    rm_v1::Router<kMethods, RouteId> router_;
};

}  // namespace

RB_ARM(RegexMatcherV1Arm)
