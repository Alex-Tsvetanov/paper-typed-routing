#include "core/table.hpp"

#include <algorithm>
#include <cmath>
#include <memory>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>

#include "core/rng.hpp"

namespace rb {
namespace {

constexpr std::size_t kTopWords = 32;
constexpr std::size_t kWords = 4096;
constexpr std::uint64_t kVocabularySeed = 0x5eedULL;

// The same vocabulary for every table: pseudo-words that alternate consonants and vowels,
// of 3 to 10 letters, or of 12 to 24 for the exploratory long vocabulary.
std::vector<std::string> make_vocabulary(std::size_t min_len, std::size_t spread) {
    static constexpr std::string_view kCons = "bcdfghjklmnprstvz";
    static constexpr std::string_view kVow = "aeiou";
    SplitMix64 rng(kVocabularySeed);
    std::unordered_set<std::string> seen;
    std::vector<std::string> out;
    while (out.size() < kWords) {
        const std::size_t len = min_len + static_cast<std::size_t>(rng.below(spread));
        std::string w;
        for (std::size_t i = 0; i < len; ++i) {
            const std::string_view set = (i % 2 == 0) ? kCons : kVow;
            w += set[static_cast<std::size_t>(rng.below(set.size()))];
        }
        if (seen.insert(w).second) {
            out.push_back(std::move(w));
        }
    }
    return out;
}

const std::vector<std::string>& vocabulary(bool long_words = false) {
    static const std::vector<std::string> words = make_vocabulary(3, 8);
    static const std::vector<std::string> long_ones = make_vocabulary(12, 13);
    return long_words ? long_ones : words;
}

// The kinds of segment at each position, per shape.
std::vector<Seg> layout(Shape s) {
    switch (s) {
        case Shape::Static: return {Seg::Literal, Seg::Literal, Seg::Literal};
        case Shape::ParamLast: return {Seg::Literal, Seg::Literal, Seg::Param};
        case Shape::ParamFirst: return {Seg::Param, Seg::Literal, Seg::Literal};
        case Shape::Rest: return {Seg::Literal, Seg::Param, Seg::Literal, Seg::Param};
        case Shape::Wild: return {Seg::Literal, Seg::Literal, Seg::Rest};
        case Shape::MixedDisjoint:
        case Shape::MixedOverlap:
        case Shape::Github: break;  // not one layout (see the *_table functions below)
    }
    return {};
}

constexpr Method kMethodOrder[] = {Method::Get, Method::Post, Method::Put, Method::Delete,
                                   Method::Patch, Method::Head, Method::Options};

std::string token(SplitMix64& rng) {
    static constexpr std::string_view kChars = "abcdefghijklmnopqrstuvwxyz0123456789";
    const std::size_t len = 1 + static_cast<std::size_t>(rng.below(12));
    std::string t;
    for (std::size_t i = 0; i < len; ++i) {
        t += kChars[static_cast<std::size_t>(rng.below(kChars.size()))];
    }
    return t;
}

// The reference matcher: in a one-shape table a path matches the route whose literals equal
// the path's segments at the literal positions, if the segment count fits the shape.
class Reference {
public:
    explicit Reference(const Table& t) : kinds_(layout(t.spec.shape)) {
        for (RouteId id = 0; id < t.routes.size(); ++id) {
            index_.emplace(key(t.routes[id].method, literals_of(t.routes[id])), id);
        }
    }

    RouteId match(Method m, std::string_view path) const {
        std::vector<std::string_view> segs;
        for (std::size_t pos = 1; pos <= path.size();) {
            const std::size_t slash = path.find('/', pos);
            const std::size_t end = slash == std::string_view::npos ? path.size() : slash;
            segs.push_back(path.substr(pos, end - pos));
            pos = end + 1;
        }
        const bool rest = kinds_.back() == Seg::Rest;
        if (rest ? segs.size() < kinds_.size() : segs.size() != kinds_.size()) {
            return kNoRoute;
        }
        std::string lits;
        for (std::size_t i = 0; i < kinds_.size(); ++i) {
            if (segs[i].empty()) {
                return kNoRoute;
            }
            if (kinds_[i] == Seg::Literal) {
                lits += segs[i];
                lits += '/';
            }
        }
        for (std::size_t i = kinds_.size(); i < segs.size(); ++i) {
            if (segs[i].empty()) {
                return kNoRoute;
            }
        }
        const auto it = index_.find(key(m, lits));
        return it == index_.end() ? kNoRoute : it->second;
    }

private:
    static std::string literals_of(const Route& r) {
        std::string s;
        for (const Segment& seg : r.segs) {
            if (seg.kind == Seg::Literal) {
                s += seg.text;
                s += '/';
            }
        }
        return s;
    }
    static std::string key(Method m, const std::string& lits) {
        return std::string(method_name(m)) + ' ' + lits;
    }

    std::vector<Seg> kinds_;
    std::unordered_map<std::string, RouteId> index_;
};

std::vector<std::string_view> split_path(std::string_view path) {
    std::vector<std::string_view> segs;
    if (path.size() <= 1) {
        return segs;  // "/" has none
    }
    for (std::size_t pos = 1; pos <= path.size();) {
        const std::size_t slash = path.find('/', pos);
        const std::size_t end = slash == std::string_view::npos ? path.size() : slash;
        segs.push_back(path.substr(pos, end - pos));
        pos = end + 1;
    }
    return segs;
}

// The reference matcher for tables of more than one layout (mixed, github): every route of
// the method that matches, and of those the most specific (a literal before a parameter
// before a catch-all, at the first segment where two routes differ), with its captured
// values. Routes are bucketed by method, first literal and (without a catch-all) segment
// count, so a query looks at few of them.
class GeneralReference {
public:
    explicit GeneralReference(const Table& t) : t_(t) {
        for (RouteId id = 0; id < t.routes.size(); ++id) {
            const Route& r = t.routes[id];
            const std::string_view first =
                !r.segs.empty() && r.segs[0].kind == Seg::Literal ? std::string_view(r.segs[0].text) : "";
            if (!r.segs.empty() && r.segs.back().kind == Seg::Rest) {
                rest_[key(r.method, 0, first)].push_back(id);
            } else {
                fixed_[key(r.method, r.segs.size(), first)].push_back(id);
            }
        }
    }

    RouteId match(Method m, std::string_view path, std::vector<std::string>& caps) const {
        const std::vector<std::string_view> segs = split_path(path);
        caps.clear();
        for (std::string_view seg : segs) {
            if (seg.empty()) {
                return kNoRoute;
            }
        }
        RouteId best = kNoRoute;
        const auto scan = [&](const std::unordered_map<std::string, std::vector<RouteId>>& index, std::size_t n,
                              std::string_view first) {
            const auto it = index.find(key(m, n, first));
            if (it == index.end()) {
                return;
            }
            for (RouteId id : it->second) {
                if (matches(t_.routes[id], segs) && (best == kNoRoute || more_specific(t_.routes[id], t_.routes[best]))) {
                    best = id;
                }
            }
        };
        const std::string_view first = segs.empty() ? std::string_view() : segs[0];
        scan(fixed_, segs.size(), first);
        scan(fixed_, segs.size(), "");
        scan(rest_, 0, first);
        scan(rest_, 0, "");
        if (best != kNoRoute) {
            const Route& r = t_.routes[best];
            std::size_t at = 0;  // offset of segment i's first byte
            for (std::size_t i = 0; i < r.segs.size(); ++i) {
                if (r.segs[i].kind == Seg::Param) {
                    caps.emplace_back(segs[i]);
                } else if (r.segs[i].kind == Seg::Rest) {
                    caps.emplace_back(path.substr(at + 1));
                }
                at += 1 + segs[i].size();
            }
        }
        return best;
    }

private:
    static std::string key(Method m, std::size_t n, std::string_view first) {
        return std::string(method_name(m)) + '|' + std::to_string(n) + '|' + std::string(first);
    }

    // As in Reference: a path with an empty segment matches no route (no empty parameter, no
    // trailing slash), so only the segment count and the literals decide.
    static bool matches(const Route& r, const std::vector<std::string_view>& segs) {
        const bool rest = !r.segs.empty() && r.segs.back().kind == Seg::Rest;
        if (rest ? segs.size() < r.segs.size() : segs.size() != r.segs.size()) {
            return false;
        }
        for (std::size_t i = 0; i < r.segs.size(); ++i) {
            if (r.segs[i].kind == Seg::Literal && r.segs[i].text != segs[i]) {
                return false;
            }
        }
        return true;
    }

    static int rank(Seg k) { return k == Seg::Literal ? 0 : (k == Seg::Param ? 1 : 2); }

    static bool more_specific(const Route& a, const Route& b) {
        for (std::size_t i = 0; i < a.segs.size() && i < b.segs.size(); ++i) {
            if (rank(a.segs[i].kind) != rank(b.segs[i].kind)) {
                return rank(a.segs[i].kind) < rank(b.segs[i].kind);
            }
        }
        return false;
    }

    const Table& t_;
    std::unordered_map<std::string, std::vector<RouteId>> fixed_;
    std::unordered_map<std::string, std::vector<RouteId>> rest_;
};

// The rendered routes, and the digest over them. Two equal routes (same method, same
// pattern) are a generator bug, refused here rather than left to the arms.
// Route ids by a Zipf law over a rank order drawn from the ring seed (see RingSpec). The
// cumulative weights are summed once in double precision; a draw is a binary search of a
// uniform [0, 1) value from the ring's generator.
class ZipfDraw {
public:
    ZipfDraw(std::size_t m, double s, std::uint64_t seed) {
        if (s <= 0.0) {
            return;
        }
        order_.resize(m);
        for (std::size_t i = 0; i < m; ++i) {
            order_[i] = static_cast<RouteId>(i);
        }
        SplitMix64 rng(seed ^ 0x21bf5eedULL);
        for (std::size_t i = m; i > 1; --i) {
            std::swap(order_[i - 1], order_[static_cast<std::size_t>(rng.below(i))]);
        }
        cdf_.resize(m);
        double sum = 0.0;
        for (std::size_t k = 0; k < m; ++k) {
            sum += 1.0 / std::pow(static_cast<double>(k + 1), s);
            cdf_[k] = sum;
        }
        for (double& c : cdf_) {
            c /= sum;
        }
    }
    bool empty() const { return order_.empty(); }
    RouteId draw(SplitMix64& rng) const {
        const double u = static_cast<double>(rng.next() >> 11) * 0x1.0p-53;
        const auto it = std::upper_bound(cdf_.begin(), cdf_.end(), u);
        const std::size_t k = std::min<std::size_t>(static_cast<std::size_t>(it - cdf_.begin()), cdf_.size() - 1);
        return order_[k];
    }

private:
    std::vector<RouteId> order_;
    std::vector<double> cdf_;
};

Table finish(Table t) {
    std::string text;
    std::unordered_set<std::string> seen;
    for (const Route& r : t.routes) {
        std::string line = std::string(method_name(r.method)) + ' ' + render(r);
        if (!seen.insert(line).second) {
            throw std::logic_error("generated table has the route " + line + " twice");
        }
        text += line;
        text += '\n';
    }
    t.digest = sha256_hex(text);
    return t;
}

constexpr std::size_t kGroup = 4;          // routes per group in the mixed shapes
constexpr std::size_t kHalfTop = kTopWords / 2;

// Draws a code in [0, range) that `used` has not seen for this method slot.
std::uint64_t draw_unique(SplitMix64& rng, std::unordered_set<std::uint64_t>& used, std::uint64_t range,
                          std::uint64_t slot, std::uint64_t slots) {
    std::uint64_t code = 0;
    do {
        code = rng.below(range);
    } while (!used.insert(code * slots + slot).second);
    return code;
}

void check_capacity(const TableSpec& spec, std::uint64_t groups, std::uint64_t capacity) {
    if (groups > capacity * 9 / 10) {
        throw std::invalid_argument("shape " + std::string(shape_name(spec.shape)) + " holds at most " +
                                    std::to_string(capacity * 9 / 10 * kGroup) + " routes here");
    }
}

Table mixed_disjoint_table(const TableSpec& spec) {
    const std::vector<std::string>& words = vocabulary(spec.long_words);
    const std::uint64_t groups = (spec.m + kGroup - 1) / kGroup;
    check_capacity(spec, groups, static_cast<std::uint64_t>(kHalfTop) * kWords * spec.methods);
    SplitMix64 rng(spec.seed);
    std::unordered_set<std::uint64_t> used_literal;
    std::unordered_set<std::uint64_t> used_resource;
    Table t;
    t.spec = spec;
    t.routes.reserve(spec.m);
    std::string top;
    std::string res;
    std::string sub;
    for (std::uint32_t i = 0; i < spec.m; ++i) {
        const std::uint64_t slot = (i / kGroup) % spec.methods;
        const Method method = kMethodOrder[slot];
        const std::size_t k = i % kGroup;
        if (k == 0) {
            // A fully literal route under one of the first 16 top words.
            const std::uint64_t range = static_cast<std::uint64_t>(kHalfTop) * kWords * kWords;
            std::uint64_t code = draw_unique(rng, used_literal, range, slot, spec.methods);
            const std::size_t c = static_cast<std::size_t>(code % kWords);
            code /= kWords;
            const std::size_t b = static_cast<std::size_t>(code % kWords);
            const std::size_t a = static_cast<std::size_t>(code / kWords);
            t.routes.push_back({method, {{Seg::Literal, words[a]}, {Seg::Literal, words[b]}, {Seg::Literal, words[c]}}});
            continue;
        }
        if (k == 1) {
            // A resource under one of the other 16 top words.
            const std::uint64_t code =
                draw_unique(rng, used_resource, static_cast<std::uint64_t>(kHalfTop) * kWords, slot, spec.methods);
            top = words[kHalfTop + static_cast<std::size_t>(code / kWords)];
            res = words[static_cast<std::size_t>(code % kWords)];
            sub = words[static_cast<std::size_t>(rng.below(kWords))];
        }
        Route r{method, {{Seg::Literal, top}, {Seg::Literal, res}, {Seg::Param, "p0"}}};
        if (k >= 2) {
            r.segs.push_back({Seg::Literal, sub});
        }
        if (k >= 3) {
            r.segs.push_back({Seg::Param, "p1"});
        }
        t.routes.push_back(std::move(r));
    }
    return finish(std::move(t));
}

Table mixed_overlap_table(const TableSpec& spec) {
    const std::vector<std::string>& words = vocabulary(spec.long_words);
    const std::uint64_t groups = (spec.m + kGroup - 1) / kGroup;
    check_capacity(spec, groups, static_cast<std::uint64_t>(kTopWords) * kWords * spec.methods);
    SplitMix64 rng(spec.seed);
    std::unordered_set<std::uint64_t> used_resource;  // (t, r) per method
    std::unordered_set<std::uint64_t> used_second;    // (t, s2) per method: /t/{p0}/s2/{p1} once
    std::unordered_set<std::uint64_t> used_first;     // (t, s1) per method
    Table t;
    t.spec = spec;
    t.routes.reserve(spec.m);
    t.decoy.assign(spec.m, std::string());
    std::size_t top = 0;
    std::string res;
    std::string s1;
    std::string s2;
    for (std::uint32_t i = 0; i < spec.m; ++i) {
        const std::uint64_t slot = (i / kGroup) % spec.methods;
        const Method method = kMethodOrder[slot];
        const std::size_t k = i % kGroup;
        if (k == 0) {
            const std::uint64_t code =
                draw_unique(rng, used_resource, static_cast<std::uint64_t>(kTopWords) * kWords, slot, spec.methods);
            top = static_cast<std::size_t>(code / kWords);
            res = words[static_cast<std::size_t>(code % kWords)];
            // s1 never equals an s2 of the same top word and method, in this group or another,
            // so /t/r/s1/{p0} and /t/{p0}/s2/{p1} of two groups never match one path: the only
            // overlaps are those inside a group, where the more specific route comes first.
            const auto key = [&](std::size_t w) {
                return (static_cast<std::uint64_t>(top) * kWords + w) * spec.methods + slot;
            };
            std::size_t w1 = 0;
            do {
                w1 = static_cast<std::size_t>(rng.below(kWords));
            } while (used_second.count(key(w1)) != 0);
            std::size_t w2 = 0;
            do {
                w2 = static_cast<std::size_t>(rng.below(kWords));
            } while (w2 == w1 || used_first.count(key(w2)) != 0 || !used_second.insert(key(w2)).second);
            used_first.insert(key(w1));
            s1 = words[w1];
            s2 = words[w2];
        }
        const std::string& tw = words[top];
        switch (k) {
            case 0: t.routes.push_back({method, {{Seg::Literal, tw}, {Seg::Literal, res}, {Seg::Literal, s1}}}); break;
            case 1: t.routes.push_back({method, {{Seg::Literal, tw}, {Seg::Literal, res}, {Seg::Param, "p0"}}}); break;
            case 2:
                t.routes.push_back(
                    {method, {{Seg::Literal, tw}, {Seg::Literal, res}, {Seg::Literal, s1}, {Seg::Param, "p0"}}});
                break;
            default:
                t.routes.push_back(
                    {method, {{Seg::Literal, tw}, {Seg::Param, "p0"}, {Seg::Literal, s2}, {Seg::Param, "p1"}}});
                t.decoy[i] = res;
                break;
        }
    }
    return finish(std::move(t));
}

Table github_table(const TableSpec& spec) {
    Table t;
    t.spec = spec;
    t.spec.m = kGithubRoutes;
    for (const auto& [method, text] : github_api_routes()) {
        t.routes.push_back(parse_route(method, text));
    }
    if (t.routes.size() != kGithubRoutes) {
        throw std::logic_error("the GitHub API list does not have 203 routes");
    }
    return finish(std::move(t));
}

// A model of router v2's segment trie over the routes that have a parameter (see RingWalk).
class TrieModel {
public:
    explicit TrieModel(const Table& t) {
        const auto is_literal = [](const Route& r) {
            bool literal = true;
            for (const Segment& s : r.segs) {
                literal = literal && s.kind == Seg::Literal;
            }
            return literal;
        };
        std::unordered_set<unsigned> param_methods;  // methods with a parameter route
        for (const Route& r : t.routes) {
            if (!is_literal(r)) {
                param_methods.insert(static_cast<unsigned>(r.method));
            }
        }
        for (RouteId id = 0; id < t.routes.size(); ++id) {
            const Route& r = t.routes[id];
            if (is_literal(r) && param_methods.count(static_cast<unsigned>(r.method)) == 0) {
                exact_.insert(std::string(method_name(r.method)) + ' ' + render(r));
                continue;
            }
            std::uint32_t node = root(r.method);
            for (const Segment& s : r.segs) {
                if (s.kind == Seg::Literal) {
                    const auto it = nodes_[node].lit.find(s.text);
                    node = it != nodes_[node].lit.end() ? it->second : child(node, &Node::lit, s.text);
                } else if (s.kind == Seg::Param) {
                    node = nodes_[node].param != kNone ? nodes_[node].param : child(node, &Node::param);
                } else {
                    node = nodes_[node].rest != kNone ? nodes_[node].rest : child(node, &Node::rest);
                }
            }
            nodes_[node].route = id;
        }
    }

    // Adds this query's walk to w.
    void walk(Method m, std::string_view path, RingWalk& w) const {
        if (exact_.count(std::string(method_name(m)) + ' ' + std::string(path)) != 0) {
            ++w.exact;
            return;
        }
        const auto it = roots_.find(static_cast<unsigned>(m));
        if (it == roots_.end()) {
            return;
        }
        const std::vector<std::string_view> segs = split_path(path);
        std::uint64_t pops = 0;
        dfs(it->second, segs, 0, pops);
        w.backtracking += pops != 0;
        w.pops += pops;
    }

private:
    static constexpr std::uint32_t kNone = 0xFFFFFFFFu;
    struct Node {
        std::unordered_map<std::string, std::uint32_t> lit;
        std::uint32_t param = kNone;
        std::uint32_t rest = kNone;
        RouteId route = kNoRoute;
        int kinds() const { return !lit.empty() + (param != kNone) + (rest != kNone); }
    };

    std::uint32_t root(Method m) {
        const auto it = roots_.find(static_cast<unsigned>(m));
        if (it != roots_.end()) {
            return it->second;
        }
        nodes_.emplace_back();
        roots_[static_cast<unsigned>(m)] = static_cast<std::uint32_t>(nodes_.size() - 1);
        return static_cast<std::uint32_t>(nodes_.size() - 1);
    }
    std::uint32_t child(std::uint32_t parent, std::uint32_t Node::*slot) {
        nodes_.emplace_back();
        const auto id = static_cast<std::uint32_t>(nodes_.size() - 1);
        nodes_[parent].*slot = id;
        return id;
    }
    std::uint32_t child(std::uint32_t parent, std::unordered_map<std::string, std::uint32_t> Node::*, const std::string& text) {
        nodes_.emplace_back();
        const auto id = static_cast<std::uint32_t>(nodes_.size() - 1);
        nodes_[parent].lit.emplace(text, id);
        return id;
    }

    // The walk of route_table.hpp's walk(): a literal child first, then a parameter, then a
    // catch-all; a failed branch returns to the last node that had another kind of child
    // (a pop) and tries that. A catch-all ends the walk.
    RouteId dfs(std::uint32_t id, const std::vector<std::string_view>& segs, std::size_t i, std::uint64_t& pops) const {
        const Node& n = nodes_[id];
        if (i == segs.size()) {
            return n.route;
        }
        const std::string_view seg = segs[i];
        const auto it = n.lit.find(std::string(seg));
        if (it != n.lit.end()) {
            const RouteId r = dfs(it->second, segs, i + 1, pops);
            if (r != kNoRoute) {
                return r;
            }
            if (n.kinds() <= 1) {
                return kNoRoute;
            }
            ++pops;
        }
        if (!seg.empty() && n.param != kNone) {
            const RouteId r = dfs(n.param, segs, i + 1, pops);
            if (r != kNoRoute) {
                return r;
            }
            if (n.rest == kNone) {
                return kNoRoute;
            }
            ++pops;
        }
        if (n.rest != kNone) {
            return nodes_[n.rest].route;  // the remainder is not empty: i < segs.size()
        }
        return kNoRoute;
    }

    std::vector<Node> nodes_;
    std::unordered_map<unsigned, std::uint32_t> roots_;
    std::unordered_set<std::string> exact_;
};

}  // namespace

std::string_view shape_name(Shape s) {
    switch (s) {
        case Shape::Static: return "static";
        case Shape::ParamLast: return "param-last";
        case Shape::ParamFirst: return "param-first";
        case Shape::Rest: return "rest";
        case Shape::Wild: return "wild";
        case Shape::MixedDisjoint: return "mixed-disjoint";
        case Shape::MixedOverlap: return "mixed-overlap";
        case Shape::Github: return "github";
    }
    return "static";
}

bool parse_shape(std::string_view text, Shape& out) {
    for (Shape s : kShapes) {
        if (shape_name(s) == text) {
            out = s;
            return true;
        }
    }
    if (text == "github") {
        out = Shape::Github;
        return true;
    }
    return false;
}

Table generate_table(const TableSpec& spec) {
    if (spec.methods < 1 || spec.methods > kMethods) {
        throw std::invalid_argument("methods must be in [1, 7]");
    }
    if (spec.shape == Shape::MixedDisjoint) {
        return mixed_disjoint_table(spec);
    }
    if (spec.shape == Shape::MixedOverlap) {
        return mixed_overlap_table(spec);
    }
    if (spec.shape == Shape::Github) {
        return github_table(spec);
    }
    const std::vector<Seg> kinds = layout(spec.shape);
    std::vector<std::size_t> radix;  // vocabulary size of each literal slot
    for (Seg k : kinds) {
        if (k == Seg::Literal) {
            radix.push_back(radix.empty() ? kTopWords : kWords);
        }
    }
    std::uint64_t capacity = 1;
    for (std::size_t r : radix) {
        capacity *= r;
    }
    capacity *= spec.methods;
    if (spec.m > capacity * 9 / 10) {
        throw std::invalid_argument("shape " + std::string(shape_name(spec.shape)) + " holds at most " +
                                    std::to_string(capacity * 9 / 10) + " routes here");
    }

    const std::vector<std::string>& words = vocabulary(spec.long_words);
    SplitMix64 rng(spec.seed);
    std::unordered_set<std::uint64_t> used;
    Table t;
    t.spec = spec;
    t.routes.reserve(spec.m);
    std::string text;
    for (std::uint32_t i = 0; i < spec.m; ++i) {
        const Method method = kMethodOrder[i % spec.methods];
        const std::uint64_t per_method = capacity / spec.methods;
        std::uint64_t code = 0;
        do {
            code = rng.below(per_method);
        } while (!used.insert(code * spec.methods + i % spec.methods).second);
        Route r{method, {}};
        std::size_t lit = 0;
        std::size_t param = 0;
        std::vector<std::size_t> picks(radix.size());
        for (std::size_t s = radix.size(); s-- > 0;) {
            picks[s] = static_cast<std::size_t>(code % radix[s]);
            code /= radix[s];
        }
        for (Seg k : kinds) {
            if (k == Seg::Literal) {
                r.segs.push_back({Seg::Literal, words[picks[lit++]]});
            } else {
                r.segs.push_back({k, "p" + std::to_string(param++)});
            }
        }
        text += method_name(method);
        text += ' ';
        text += render(r);
        text += '\n';
        t.routes.push_back(std::move(r));
    }
    t.digest = sha256_hex(text);
    return t;
}

Ring generate_ring(const Table& table, const RingSpec& spec) {
    if (table.routes.empty() || spec.size == 0) {
        throw std::invalid_argument("generate_ring: empty table or ring");
    }
    const bool general = table.spec.shape == Shape::MixedDisjoint || table.spec.shape == Shape::MixedOverlap ||
                         table.spec.shape == Shape::Github;
    std::unique_ptr<Reference> ref;
    std::unique_ptr<GeneralReference> gref;
    if (general) {
        gref = std::make_unique<GeneralReference>(table);
    } else {
        ref = std::make_unique<Reference>(table);
    }
    SplitMix64 rng(spec.seed);
    Ring ring;
    ring.spec = spec;
    ring.queries.reserve(spec.size);
    const ZipfDraw zipf(table.routes.size(), spec.zipf, spec.seed);
    std::string text = table.digest + '\n';
    for (std::uint32_t i = 0; i < spec.size; ++i) {
        const auto id = zipf.empty() ? static_cast<RouteId>(rng.below(table.routes.size())) : zipf.draw(rng);
        const bool miss = spec.miss_permille > 0 && rng.below(1000) < spec.miss_permille;
        const Route& r = table.routes[id];
        Query q{r.method, {}, miss ? kNoRoute : id, {}};
        std::size_t last_literal = 0;
        for (std::size_t s = 0; s < r.segs.size(); ++s) {
            if (r.segs[s].kind == Seg::Literal) {
                last_literal = s;
            }
        }
        for (std::size_t s = 0; s < r.segs.size(); ++s) {
            const Segment& seg = r.segs[s];
            q.path += '/';
            if (seg.kind == Seg::Literal) {
                // A miss replaces the last literal with a word that has digits, which no
                // vocabulary word has.
                q.path += (miss && s == last_literal) ? "zz" + std::to_string(i) : seg.text;
            } else if (seg.kind == Seg::Param) {
                const bool decoy = spec.decoys && q.caps.empty() && !table.decoy.empty() &&
                                   !table.decoy[id].empty() && rng.below(2) == 0;
                q.caps.push_back(decoy ? table.decoy[id] : token(rng));
                q.path += q.caps.back();
            } else {
                std::string v = token(rng);
                for (std::uint64_t n = rng.below(3); n > 0; --n) {
                    v += '/';
                    v += token(rng);
                }
                q.path += v;
                q.caps.push_back(std::move(v));
            }
        }
        if (miss) {
            q.caps.clear();
        }
        if (general) {
            // Tables of more than one layout: the expectation is what the reference matcher
            // finds (the most specific route), whatever route the query was drawn from.
            q.expect = gref->match(q.method, q.path, q.caps);
        } else if (ref->match(q.method, q.path) != q.expect) {
            throw std::logic_error("generate_ring: reference matcher disagrees on " + q.path);
        }
        text += method_name(q.method);
        text += ' ';
        text += q.path;
        text += ' ';
        text += std::to_string(q.expect);
        text += '\n';
        ring.queries.push_back(std::move(q));
    }
    ring.digest = sha256_hex(text);
    return ring;
}

RingWalk ring_walk(const Table& table, const Ring& ring) {
    const TrieModel model(table);
    RingWalk w;
    for (const Query& q : ring.queries) {
        model.walk(q.method, q.path, w);
    }
    return w;
}

}  // namespace rb
