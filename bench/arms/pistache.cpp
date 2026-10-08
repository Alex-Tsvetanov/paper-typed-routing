// Pistache's REST router tree (Pistache::Rest::SegmentTreeNode), one per method, driven as
// Rest::Router drives it: addRoute() stores the sanitized pattern in a buffer the tree keeps
// views into (Router::addRoute), and a lookup sanitizes the request path with
// SegmentTreeNode::sanitizeResource() and calls findRoute() (Router::route). A parameter is
// ":name". Pistache's splat '*' matches one segment only, so there is no catch-all and the
// arm refuses the wild shape. Values are read as a handler reads them,
// TypedParam::as<std::string>(); the arm keeps the copies until the next lookup.
#include <pistache/router.h>

#include <array>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include "core/runner.hpp"

namespace {

using namespace rb;
namespace Rest = Pistache::Rest;

// The handler a route stores; the arm reads the route id back out of it.
struct IdHandler {
    RouteId id;
    Rest::Route::Result operator()(const Rest::Request, Pistache::Http::ResponseWriter) const {
        return Rest::Route::Result::Ok;
    }
};

class PistacheArm final {
public:
    static ArmInfo info() { return {"pistache", "pistacheio/pistache v0.4.26", "std::string per value (as<std::string>)"}; }

    void add(const Route& r, RouteId id) {
        std::string resource;
        for (const Segment& s : r.segs) {
            resource += '/';
            if (s.kind == Seg::Literal) {
                resource += s.text;
            } else if (s.kind == Seg::Param) {
                resource += ':' + s.text;
            } else {
                throw Refused("pistache: no catch-all (its splat matches one segment)");
            }
        }
        const std::string sanitized = Rest::SegmentTreeNode::sanitizeResource(resource);
        std::shared_ptr<char> ptr(new char[sanitized.length()], std::default_delete<char[]>());
        std::memcpy(ptr.get(), sanitized.data(), sanitized.length());
        try {
            trees_[static_cast<std::size_t>(r.method)].addRoute(std::string_view(ptr.get(), sanitized.length()),
                                                                IdHandler{id}, ptr);
        } catch (const std::exception& e) {
            throw Refused(std::string("pistache: ") + e.what());
        }
    }

    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        c.n = 0;
        values_.clear();
        const std::string sanitized = Rest::SegmentTreeNode::sanitizeResource(path);
        const auto [route, params, splats] =
            trees_[static_cast<std::size_t>(m)].findRoute(std::string_view(sanitized.data(), sanitized.length()));
        if (!route) {
            return kNoRoute;
        }
        for (const auto& p : params) {
            values_.push_back(p.as<std::string>());
        }
        for (const std::string& v : values_) {
            if (c.n < kMaxParams) {
                c.v[c.n++] = v;
            }
        }
        return route->handler_.target<IdHandler>()->id;
    }

private:
    std::array<Rest::SegmentTreeNode, kMethods> trees_;
    std::vector<std::string> values_;
};

}  // namespace

RB_ARM(PistacheArm)
