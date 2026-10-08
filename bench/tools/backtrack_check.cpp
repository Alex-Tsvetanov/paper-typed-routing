// backtrack_check: rbench's model of RegexMatcher v2's walk (rb::ring_walk) against a counting
// build of v2 (design/round2/engineering.md, adoption rule (b), part 3). The counting build
// defines MATCHER_ROUTE_ON_BACKTRACK, which v2's walk calls each time it leaves a branch to try
// another (at every pop of its stack; with B1's chained edges also where a path left a chain at
// a node with more than one kind of child). Over the tables and rings rbench generates: per
// table, the queries with at least one such departure and the departures, from v2 and from the
// model; the nodes of kind 2 (B1's nodes with chained edges, B1''s chain nodes); and the
// queries whose answer (route and captured values) differs from the ring's expectation.
//
//     backtrack_check [--seeds 1,2] [--ring-seeds 2,3] [--sizes 10,100,...]
//                      (default: table seed 1, ring seed 2, m = 10 to 10,000)
//
// Built from bench/core and RegexMatcher's include directory (bench/tools/CMakeLists.txt,
// REGEXMATCHER_DIR), with no arm and no fetched code. It needs a RegexMatcher with the hook.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <string_view>
#include <vector>

namespace {
std::uint64_t g_departures = 0;
}  // namespace

#define MATCHER_ROUTE_ON_BACKTRACK() (++g_departures)

#include <matcher/route.hpp>

#include "core/table.hpp"

namespace {

namespace R = matcher::route;

std::vector<std::string> split(const std::string& s) {
    std::vector<std::string> out;
    std::size_t pos = 0;
    while (pos <= s.size()) {
        const std::size_t c = s.find(',', pos);
        const std::size_t e = c == std::string::npos ? s.size() : c;
        if (e > pos) {
            out.push_back(s.substr(pos, e - pos));
        }
        pos = e + 1;
    }
    return out;
}

}  // namespace

int main(int argc, char** argv) {
    std::string seeds = "1";
    std::string ring_seeds = "2";
    std::string sizes = "10,100,1000,10000";
    for (int i = 1; i + 1 < argc; i += 2) {
        const std::string k = argv[i];
        if (k == "--seeds") {
            seeds = argv[i + 1];
        } else if (k == "--ring-seeds") {
            ring_seeds = argv[i + 1];
        } else if (k == "--sizes") {
            sizes = argv[i + 1];
        } else {
            std::fprintf(stderr, "usage: backtrack_check [--seeds 1,2] [--ring-seeds 2,3] [--sizes 10,100,...]\n");
            return 2;
        }
    }
    int bad = 0;
    int tables = 0;
    for (const std::string& ts : split(seeds)) {
        for (const std::string& rs : split(ring_seeds)) {
            std::vector<std::pair<rb::Shape, std::uint32_t>> want;
            for (const std::string& m : split(sizes)) {
                for (rb::Shape sh : rb::kShapes) {
                    want.emplace_back(sh, static_cast<std::uint32_t>(std::stoul(m)));
                }
            }
            want.emplace_back(rb::Shape::Github, rb::kGithubRoutes);
            for (const auto& [shape, m] : want) {
                const rb::Table t = rb::generate_table({shape, m, std::stoull(ts), 1});
                const rb::Ring r = rb::generate_ring(t, {4096, std::stoull(rs), 0});
                std::vector<std::string> patterns;
                std::vector<R::RouteSpec> specs;
                for (const rb::Route& route : t.routes) {
                    patterns.push_back(rb::render(route));
                }
                for (std::uint32_t i = 0; i < t.routes.size(); ++i) {
                    specs.push_back({static_cast<unsigned>(t.routes[i].method), patterns[i], i});
                }
                const R::Built b = R::build_table(specs);
                ++tables;
                if (b.error != R::BuildError::None) {
                    std::printf("%s %u: build error\n", std::string(rb::shape_name(shape)).c_str(), m);
                    ++bad;
                    continue;
                }
                std::uint64_t queries = 0;
                std::uint64_t departures = 0;
                std::uint64_t wrong = 0;
                std::uint64_t chained = 0;  // nodes of kind 2: B1's chained-edge nodes, B1''s chain nodes
                for (const R::Node& n : b.nodes) {
                    chained += n.hashed == 2;
                }
                for (const rb::Query& q : r.queries) {
                    g_departures = 0;
                    const R::Match mt = R::find(b.view(), static_cast<unsigned>(q.method), q.path);
                    queries += g_departures != 0;
                    departures += g_departures;
                    const std::uint32_t got = mt.status == R::Status::Found ? mt.route : rb::kNoRoute;
                    bool same = got == q.expect;
                    if (same && got != rb::kNoRoute) {
                        same = mt.count == q.caps.size();
                        for (std::size_t i = 0; same && i < q.caps.size(); ++i) {
                            same = mt.params[i].view() == q.caps[i];
                        }
                    }
                    wrong += !same;
                }
                const rb::RingWalk w = rb::ring_walk(t, r);
                const bool ok = w.backtracking == queries && w.pops == departures && wrong == 0;
                bad += !ok;
                std::printf("%-14s %6u  seeds %s:%s  kind-2 nodes %6llu  v2: %5llu queries, %6llu departures   "
                            "model: %5u queries, %6llu pops  %s%s\n",
                            std::string(rb::shape_name(shape)).c_str(), static_cast<unsigned>(t.routes.size()),
                            ts.c_str(), rs.c_str(), static_cast<unsigned long long>(chained),
                            static_cast<unsigned long long>(queries), static_cast<unsigned long long>(departures),
                            w.backtracking, static_cast<unsigned long long>(w.pops),
                            w.backtracking == queries && w.pops == departures ? "same" : "DIFFERENT",
                            wrong ? " (answers differ from the ring's)" : "");
            }
        }
    }
    std::printf("%d tables; %s\n", tables,
                bad == 0 ? "the model counts what v2 does on every table, and every answer is the ring's"
                         : "the model and v2 differ, or an answer does");
    return bad == 0 ? 0 : 1;
}
