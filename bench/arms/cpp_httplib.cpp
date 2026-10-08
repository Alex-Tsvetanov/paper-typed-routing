// cpp-httplib v0.58.0: the route matching of httplib::Server (httplib.h), transcribed from
// Server::dispatch_request, which a lookup needs without a running server. Each method has a list
// of (matcher, route) in registration order, and the first matcher that matches wins. A matcher
// is chosen as Server::make_matcher chooses it: detail::PathParamsMatcher for a pattern with
// "/:" or with no regular-expression character, detail::RegexMatcher (std::regex_match over
// the whole path) otherwise. A parameter is :name; cpp-httplib has no catch-all syntax, so its
// documented way, a regular expression, stands for one: "(.+)" as the last segment, whose value
// is the regular expression's first group. Precedence is registration order; the mixed-overlap
// tables register the more specific route of a pair first (core/table.hpp). The path is copied
// into the arm's reused httplib::Request, as the server's request carries it; its capacity is
// kept, so a lookup does not allocate for it. cpp-httplib has no 405 of its own: the harness's
// rule applies.
#include <httplib.h>

#include <memory>
#include <string>
#include <vector>

#include "core/runner.hpp"

namespace {

using namespace rb;

class HttplibArm final {
public:
    static ArmInfo info() {
        return {"cpp-httplib", "yhirose/cpp-httplib v0.58.0 (Server's route matching)",
                "copies (path parameters in a map; a regular expression's groups as views)"};
    }

    void add(const Route& r, RouteId id) {
        std::string pattern;
        std::vector<std::string> names;
        bool rest = false;
        for (const Segment& s : r.segs) {
            pattern += '/';
            if (s.kind == Seg::Literal) {
                pattern += s.text;
            } else if (s.kind == Seg::Param) {
                pattern += ":" + s.text;
                names.push_back(s.text);
            } else {
                pattern += "(.+)";
                rest = true;
            }
        }
        if (rest && !names.empty()) {
            throw Refused("cpp-httplib: a pattern cannot hold both a path parameter and a regular expression");
        }
        auto& list = routes_[static_cast<std::size_t>(r.method)];
        list.push_back({make_matcher(pattern), id, std::move(names), rest});
    }

    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        req_.path.assign(path);
        c.n = 0;
        for (const Entry& e : routes_[static_cast<std::size_t>(m)]) {
            if (!e.matcher->match(req_)) {
                continue;
            }
            if (e.regex) {
                for (std::size_t g = 1; g < req_.matches.size() && c.n < kMaxParams; ++g) {
                    c.v[c.n++] = std::string_view(&*req_.matches[g].first, req_.matches[g].length());
                }
            } else {
                for (const std::string& name : e.names) {
                    const auto it = req_.path_params.find(name);
                    if (it != req_.path_params.end() && c.n < kMaxParams) {
                        c.v[c.n++] = it->second;
                    }
                }
            }
            return e.id;
        }
        return kNoRoute;
    }

private:
    struct Entry {
        std::unique_ptr<httplib::detail::MatcherBase> matcher;
        RouteId id;
        std::vector<std::string> names;
        bool regex;
    };

    // Server::make_matcher (httplib.h), which is private to Server.
    static std::unique_ptr<httplib::detail::MatcherBase> make_matcher(const std::string& pattern) {
        if (pattern.find("/:") != std::string::npos) {
            return std::make_unique<httplib::detail::PathParamsMatcher>(pattern);
        }
        if (pattern.find_first_of(".^$|()[]{}*+?\\") == std::string::npos) {
            return std::make_unique<httplib::detail::PathParamsMatcher>(pattern);
        }
        return std::make_unique<httplib::detail::RegexMatcher>(pattern);
    }

    std::array<std::vector<Entry>, kMethods> routes_;
    httplib::Request req_;
};

}  // namespace

RB_ARM(HttplibArm)
