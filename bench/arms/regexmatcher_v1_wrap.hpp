// RegexMatcher v1 (the regex-set engine at commit d16f30a8) as a route matcher: the
// pattern-to-regex wrapper of the regexmatcher-v1 reference arm, shared with the paper's server
// (its v1 router arm, the reference of H6). One union automaton per method, built from the
// expressions the pre-v2 routers wrote: a literal segment escaped, a parameter
// ([A-Za-z0-9_.%\-]+), a catch-all ([A-Za-z0-9_.%\-\/]+); compile() after the last route.
// match_with_groups returns every matching route; the lowest route id wins. Captured values are
// the reported offsets into the path. The parameter class is narrower than an RFC 3986 pchar, so
// the wrapper fails the pchar probes (design/round2/hypotheses-v2-proposal.md, H5(b)).
#pragma once

#include <matcher/core.hpp>

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace rm_v1 {

enum class SegKind : std::uint8_t { Literal, Param, Rest };

// The regular expression of one route, from its segments.
template <class Segments>
std::string pattern_regex(const Segments& segs) {
    std::string re;
    for (const auto& s : segs) {
        re += "\\/";
        if (s.kind == SegKind::Literal) {
            for (const char ch : s.text) {
                if (std::string_view(R"(.+?()[]^$|\*{})").find(ch) != std::string_view::npos) {
                    re += '\\';
                }
                re += ch;
            }
        } else {
            re += s.kind == SegKind::Param ? R"(([A-Za-z0-9_.%\-]+))" : R"(([A-Za-z0-9_.%\-\/]+))";
        }
    }
    return re;
}

struct Result {
    std::uint32_t route = 0xFFFF'FFFFu;  // 0xFFFFFFFF: no route of this method matches
    std::size_t count = 0;
    std::array<std::string_view, 16> values{};
};

// Routes of up to Methods methods; add, then compile, then match.
template <std::size_t Methods, class Id = std::uint32_t>
class Router {
public:
    void add(std::size_t method, const std::string& regex, Id id) { matchers_[method].add_regex(regex, id); }

    void compile() {
        for (auto& m : matchers_) {
            m.compile();
        }
    }

    // The lowest matching route of this method, and its captured values as views into path.
    Result match(std::size_t method, std::string_view path) {
        Result out;
        results_ = matchers_[method].match_with_groups(path);
        if (results_.empty()) {
            return out;
        }
        const auto* best = &results_.front();
        for (const auto& res : results_) {
            if (res.regex_id < best->regex_id) {
                best = &res;
            }
        }
        out.route = best->regex_id;
        for (const auto& [group, pos] : best->groups) {
            if (out.count < out.values.size() && pos.first <= pos.second && pos.second <= path.size()) {
                out.values[out.count++] = path.substr(pos.first, pos.second - pos.first);
            }
        }
        return out;
    }

private:
    std::array<matcher::RegexMatcher<Id, char>, Methods> matchers_;
    std::vector<matcher::MatchResult<Id>> results_;  // kept between lookups; the engine returns a new one per call
};

}  // namespace rm_v1
