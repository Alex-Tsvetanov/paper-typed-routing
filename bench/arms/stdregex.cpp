// In-repo baseline: one std::regex per route, tried in registration order; the first full
// match wins. A parameter is ([^/]+) and a catch-all is (.+). Captures are views into the
// query path, read from a match_results the arm keeps between lookups.
#include <array>
#include <regex>
#include <string>
#include <vector>

#include "core/runner.hpp"

namespace {

using namespace rb;

class StdRegexArm final {
public:
    static ArmInfo info() { return {"std-regex", "standard library", "views into the path"}; }

    void add(const Route& r, RouteId id) {
        std::string re;
        for (const Segment& s : r.segs) {
            re += '/';
            if (s.kind == Seg::Literal) {
                for (const char ch : s.text) {
                    if (std::string_view(R"(\^$.|?*+()[]{})").find(ch) != std::string_view::npos) {
                        re += '\\';
                    }
                    re += ch;
                }
            } else {
                re += s.kind == Seg::Param ? "([^/]+)" : "(.+)";
            }
        }
        routes_[static_cast<std::size_t>(r.method)].push_back(
            {std::regex(re, std::regex::ECMAScript | std::regex::optimize), id});
    }

    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        c.n = 0;
        for (const Entry& e : routes_[static_cast<std::size_t>(m)]) {
            if (std::regex_match(path, match_, e.re)) {
                for (std::size_t g = 1; g < match_.size() && c.n < kMaxParams; ++g) {
                    const auto at = static_cast<std::size_t>(match_[g].first - path.begin());
                    c.v[c.n++] = std::string_view(path).substr(at, static_cast<std::size_t>(match_[g].length()));
                }
                return e.id;
            }
        }
        return kNoRoute;
    }

private:
    struct Entry {
        std::regex re;
        RouteId id;
    };
    std::array<std::vector<Entry>, kMethods> routes_;
    std::smatch match_;
};

}  // namespace

RB_ARM(StdRegexArm)
