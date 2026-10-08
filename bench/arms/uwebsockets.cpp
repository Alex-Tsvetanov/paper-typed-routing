// uWebSockets v20.80.0: uWS::HttpRouter (src/HttpRouter.h), the router uWS::App routes with,
// on its own. A segment trie with the method as its first level, children ordered static, then
// parameter (':'), then wildcard ('*'), searched depth first with backtracking; a parameter is
// :name (stored positionally), a wildcard * matches the rest of the path. The route's handler
// is called during the search, as uWS::App calls it, and returns true (handled); it records the
// route id in the router's user data. Captured values are views into the path
// (getParameters()). uWS captures no value for a wildcard, so on the wild shape the answers
// differ from the design's by that value (bench/semantics.json). uWS has no 405 of its own:
// the harness's rule applies.
#include <HttpRouter.h>

#include <array>
#include <cstdint>
#include <string>
#include <string_view>

#include "core/runner.hpp"

namespace {

using namespace rb;

class UwsArm final {
public:
    static ArmInfo info() {
        return {"uwebsockets", "uNetworking/uWebSockets v20.80.0 uWS::HttpRouter", "views into the path"};
    }

    void add(const Route& r, RouteId id) {
        std::string pattern;
        for (const Segment& s : r.segs) {
            pattern += '/';
            pattern += s.kind == Seg::Literal ? s.text : (s.kind == Seg::Param ? ":" + s.text : std::string("*"));
        }
        router_.add({std::string(method_name(r.method))}, pattern, [id](uWS::HttpRouter<Data>* router) {
            router->getUserData().id = id;
            return true;
        });
    }

    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        router_.getUserData().id = kNoRoute;
        c.n = 0;
        if (!router_.route(kMethodNames[static_cast<std::size_t>(m)], path)) {
            return kNoRoute;
        }
        const auto [top, params] = router_.getParameters();
        for (int i = 0; i <= top && c.n < kMaxParams; ++i) {
            c.v[c.n++] = params[i];
        }
        return router_.getUserData().id;
    }

private:
    struct Data {
        RouteId id = kNoRoute;
    };
    static constexpr std::array<std::string_view, kMethods> kMethodNames = {"GET",   "POST", "PUT",    "DELETE",
                                                                           "PATCH", "HEAD", "OPTIONS"};
    uWS::HttpRouter<Data> router_;
};

}  // namespace

RB_ARM(UwsArm)
