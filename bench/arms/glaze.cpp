// glaze v9.0.0: glz::route_table (include/glaze/net/http_router.hpp), the route table of glaze's
// HTTP router, on its own. Paths without a parameter or wildcard go into an exact-match map
// looked up first; the rest into a segment tree whose nodes hold a map of static children, one
// parameter child and one wildcard child, searched static, parameter, wildcard with
// backtracking. A parameter is :name and a catch-all *name. match() returns the route's value
// (here the route id + 1; 0, the value's default, means no route) and the parameters in a map by
// name, as decoded strings; the adapter keeps that map until the next lookup and returns views
// into it, in the route's parameter order. glaze splits the path on '/' and skips empty
// segments, so a trailing slash is not strict; the rings of the grid never test it. glaze has no
// 405 of its own: the harness's rule applies.
#include <glaze/net/http_router.hpp>

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

#include "core/runner.hpp"

namespace {

using namespace rb;

glz::http_method to_glaze(Method m) {
    switch (m) {
        case Method::Get: return glz::http_method::GET;
        case Method::Post: return glz::http_method::POST;
        case Method::Put: return glz::http_method::PUT;
        case Method::Delete: return glz::http_method::DELETE;
        case Method::Patch: return glz::http_method::PATCH;
        case Method::Head: return glz::http_method::HEAD;
        case Method::Options: return glz::http_method::OPTIONS;
    }
    return glz::http_method::GET;
}

class GlazeArm final {
public:
    static ArmInfo info() {
        return {"glaze", "stephenberry/glaze v9.0.0 glz::route_table", "copies (decoded strings in a map)"};
    }

    void add(const Route& r, RouteId id) {
        std::string pattern;
        std::vector<std::string> names;
        for (const Segment& s : r.segs) {
            pattern += '/';
            if (s.kind == Seg::Literal) {
                pattern += s.text;
            } else {
                pattern += (s.kind == Seg::Param ? ":" : "*") + s.text;
                names.push_back(s.text);
            }
        }
        if (names_.size() <= id) {
            names_.resize(id + 1);
        }
        names_[id] = std::move(names);
        table_.add(to_glaze(r.method), pattern, id + 1);
    }

    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        auto [value, params] = table_.match(to_glaze(m), path);
        c.n = 0;
        if (value == 0) {
            return kNoRoute;
        }
        last_ = std::move(params);
        const RouteId id = value - 1;
        for (const std::string& name : names_[id]) {
            const auto it = last_.find(name);
            if (it != last_.end() && c.n < kMaxParams) {
                c.v[c.n++] = it->second;
            }
        }
        return id;
    }

private:
    glz::route_table<std::uint32_t> table_;
    std::vector<std::vector<std::string>> names_;  // per route id, its parameters' names in order
    std::unordered_map<std::string, std::string> last_;
};

}  // namespace

RB_ARM(GlazeArm)
