// The minimal server's v1 router arm: see arm_v1.hpp.
#include "arm_v1.hpp"

#include "arms/regexmatcher_v1_wrap.hpp"

namespace mserver::v1 {

namespace {

struct Seg {
    rm_v1::SegKind kind;
    std::string_view text;
};

// rbench's syntax: "{*name}" a catch-all, "{name}" (or "{name:type}") a parameter, else a
// literal segment.
std::vector<Seg> segments(std::string_view pattern) {
    std::vector<Seg> segs;
    std::string_view rest = pattern.substr(1);
    if (pattern.size() <= 1) {
        return segs;
    }
    while (true) {
        const std::size_t slash = rest.find('/');
        const std::string_view s = rest.substr(0, slash);
        if (s.size() >= 2 && s.front() == '{' && s.back() == '}') {
            segs.push_back({s[1] == '*' ? rm_v1::SegKind::Rest : rm_v1::SegKind::Param, s});
        } else {
            segs.push_back({rm_v1::SegKind::Literal, s});
        }
        if (slash == std::string_view::npos) {
            break;
        }
        rest.remove_prefix(slash + 1);
    }
    return segs;
}

}  // namespace

class Router {
public:
    rm_v1::Router<9, std::uint32_t> router;
};

std::shared_ptr<Router> make(const std::vector<std::pair<unsigned, std::string>>& routes) {
    auto r = std::make_shared<Router>();
    for (std::size_t i = 0; i < routes.size(); ++i) {
        const std::vector<Seg> segs = segments(routes[i].second);
        r->router.add(routes[i].first, segs.empty() ? std::string("\\/") : rm_v1::pattern_regex(segs),
                      static_cast<std::uint32_t>(i));
    }
    r->router.compile();
    return r;
}

void match(Router& router, unsigned method, std::string_view path, Lookup& out) {
    const rm_v1::Result r = router.router.match(method, path);
    out.route = r.route;
    out.count = r.count;
    for (std::size_t i = 0; i < r.count && i < out.values.size(); ++i) {
        out.values[i] = r.values[i];
    }
}

}  // namespace mserver::v1
