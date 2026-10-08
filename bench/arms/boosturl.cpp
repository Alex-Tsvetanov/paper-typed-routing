// The router example that ships with Boost.URL (example/router in boostorg/url at
// boost-1.92.0), one per method. A parameter is {name} and a catch-all {name+} (one or more
// segments). The query path is parsed with parse_path, as the example's server does, and
// find() fills a fixed matches array with views into the path; a lookup allocates nothing.
#include <boost/url/parse_path.hpp>

#include <array>
#include <string>

#include "core/runner.hpp"
#include "router.hpp"

namespace {

using namespace rb;

class BoostUrlArm final {
public:
    static ArmInfo info() {
        return {"boost-url", "boostorg/url boost-1.92.0 example/router", "views into the path (matches)"};
    }

    void add(const Route& r, RouteId id) {
        std::string pattern;
        for (const Segment& s : r.segs) {
            pattern += '/';
            if (s.kind == Seg::Literal) {
                pattern += s.text;
            } else {
                pattern += '{' + s.text + (s.kind == Seg::Rest ? "+}" : "}");
            }
        }
        try {
            routers_[static_cast<std::size_t>(r.method)].insert(pattern, id);
        } catch (const std::exception& e) {
            throw Refused(std::string("boost-url: ") + e.what());
        }
    }

    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        c.n = 0;
        const auto segs = boost::urls::parse_path(path);
        if (!segs) {
            return kNoRoute;
        }
        const RouteId* id = routers_[static_cast<std::size_t>(m)].find(*segs, matches_);
        if (id == nullptr) {
            return kNoRoute;
        }
        for (std::size_t i = 0; i < matches_.size() && c.n < kMaxParams; ++i) {
            c.v[c.n++] = std::string_view(matches_[i].data(), matches_[i].size());
        }
        return *id;
    }

private:
    std::array<boost::urls::router<RouteId>, kMethods> routers_;
    boost::urls::matches matches_;
};

}  // namespace

RB_ARM(BoostUrlArm)
