// test_ablation: the untimed test of the ablation copies of design/review-runs/ablations.md (ctest, built
// with the review arms, cmake/tests-review.cmake). On rbench's own tables (core/table.hpp: the seven shapes
// of the grid, 10 to 10,000 routes, table seeds 1 and 2, one and three methods) and rings with misses:
// 1. What each change does to the table, read from the built table itself:
//    copy, ab-bytes, ab-heapstack and ab-strings
//                        the same table as the pinned headers, array by array and field by field;
//    ab-linear           no node is hashed, and every node keeps its edges;
//    ab-hashed           every node with an edge is hashed;
//    ab-noexact          the exact-match table is empty, and no method is answered by it.
// 2. Every variant answers every query as the pinned code does (status, route, the methods a 405
//    allows, and every captured value as the same bytes of the same path), under the query's own
//    method and under each of the seven methods, so that 404 and 405 are both reached. ab-strings owns
//    copies of the captured bytes, so its captured values are compared byte for byte, and each must
//    not point into the path (it is a copy).
// 3. The test is not vacuous: it fails unless it compared a lookup and its pinned answers reached a 404, a
//    405 and an answer with captures. It prints how many it reached of each, then "test_ablation: ok (T
//    tables, N lookups compared, 0 failing)", or each failure; exit 1 on a failure. T and N are fixed by the
//    loops below (112 tables; 112 x 7 variants x 512 queries x 8 methods = 3211264 lookups), and
//    sanitizer_record.py requires exactly those.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include <matcher/route.hpp>

#include "arms/ablation/route_ab_bytes.hpp"
#include "arms/ablation/route_ab_hashed.hpp"
#include "arms/ablation/route_ab_heapstack.hpp"
#include "arms/ablation/route_ab_linear.hpp"
#include "arms/ablation/route_ab_noexact.hpp"
#include "arms/ablation/route_ab_strings.hpp"
#include "arms/ablation/route_copy.hpp"
#include "core/route.hpp"
#include "core/table.hpp"

namespace {

int failures = 0;
std::uint64_t compared = 0;
// What the pinned answers of the compared lookups were: no route, a 405, and a route with captured values.
std::uint64_t not_found = 0;
std::uint64_t not_allowed = 0;
std::uint64_t with_captures = 0;

void expect(bool ok, const std::string& what) {
    if (!ok) {
        if (++failures <= 50) {
            std::printf("FAIL: %s\n", what.c_str());
        }
    }
}

template <class Spec>
std::vector<Spec> specs_of(const rb::Table& t, std::vector<std::string>& patterns) {
    patterns.clear();
    for (const rb::Route& r : t.routes) {
        patterns.push_back(rb::render(r));
    }
    std::vector<Spec> specs;
    for (std::size_t i = 0; i < t.routes.size(); ++i) {
        specs.push_back({static_cast<unsigned>(t.routes[i].method), patterns[i], static_cast<std::uint32_t>(i)});
    }
    return specs;
}

// Two tables are the same when every array has the same length and the same fields.
template <class A, class B>
bool same_table(const A& a, const B& b) {
    if (a.nodes.size() != b.nodes.size() || a.edges.size() != b.edges.size() ||
        a.literals.size() != b.literals.size() || a.arena != b.arena || a.methods != b.methods ||
        a.literal_methods != b.literal_methods) {
        return false;
    }
    for (std::size_t i = 0; i < a.roots.size(); ++i) {
        if (a.roots[i] != b.roots[i]) {
            return false;
        }
    }
    for (std::size_t i = 0; i < a.nodes.size(); ++i) {
        const auto& x = a.nodes[i];
        const auto& y = b.nodes[i];
        if (x.edges != y.edges || x.count != y.count || x.hashed != y.hashed || x.branches != y.branches ||
            x.u64 != y.u64 || x.i64 != y.i64 || x.param != y.param || x.rest != y.rest || x.route != y.route) {
            return false;
        }
    }
    for (std::size_t i = 0; i < a.edges.size(); ++i) {
        const auto& x = a.edges[i];
        const auto& y = b.edges[i];
        if (x.word != y.word || x.child != y.child || x.off != y.off || x.len != y.len) {
            return false;
        }
    }
    for (std::size_t i = 0; i < a.literals.size(); ++i) {
        const auto& x = a.literals[i];
        const auto& y = b.literals[i];
        if (x.hash != y.hash || x.off != y.off || x.len != y.len || x.route != y.route || x.method != y.method) {
            return false;
        }
    }
    return true;
}

template <class V>
std::size_t hashed_nodes(const V& v) {
    std::size_t n = 0;
    for (const auto& node : v.nodes) {
        n += node.hashed != 0 ? 1 : 0;
    }
    return n;
}

template <class V>
std::size_t nodes_with_edges(const V& v) {
    std::size_t n = 0;
    for (const auto& node : v.nodes) {
        n += node.count != 0 ? 1 : 0;
    }
    return n;
}

// The answers of one variant against the pinned code's, on one lookup.
template <class M>
void same_answer(const matcher::route::Match& want, const M& got, std::string_view path, const std::string& where) {
    ++compared;
    if (want.status == matcher::route::Status::NotFound) {
        ++not_found;
    } else if (want.status == matcher::route::Status::MethodNotAllowed) {
        ++not_allowed;
    } else if (want.count > 0) {
        ++with_captures;
    }
    bool ok = static_cast<int>(want.status) == static_cast<int>(got.status) && want.route == got.route &&
              want.count == got.count && want.allowed == got.allowed;
    for (std::size_t i = 0; ok && i < want.count; ++i) {
        if constexpr (requires { got.params[i].ptr; }) {
            ok = want.params[i].ptr == got.params[i].ptr && want.params[i].len == got.params[i].len;
        } else {
            // An owned copy (ab-strings): the same bytes, held outside the path.
            const char* d = got.params[i].data();
            ok = got.params[i].size() == want.params[i].len &&
                 std::memcmp(d, want.params[i].ptr, want.params[i].len) == 0 &&
                 (want.params[i].len == 0 || d < path.data() || d >= path.data() + path.size());
        }
    }
    expect(ok, where + ": the answer differs from the pinned code's");
}

template <class NS>
struct Variant;

#define RB_TEST_VARIANT(ns)                                                                          \
    template <>                                                                                      \
    struct Variant<ns::TableView> {                                                                  \
        using Spec = ns::RouteSpec;                                                                  \
        static ns::RuntimeTable build(std::span<const Spec> s) { return ns::make_runtime_table(s); } \
        static ns::Match find(const ns::TableView& v, unsigned m, std::string_view p) {              \
            return ns::find(v, m, p);                                                                \
        }                                                                                            \
        static constexpr bool ok(const ns::RuntimeTable& t) { return t.error == ns::BuildError::None; } \
    };
RB_TEST_VARIANT(matcher::route_copy)
RB_TEST_VARIANT(matcher::route_ab_linear)
RB_TEST_VARIANT(matcher::route_ab_hashed)
RB_TEST_VARIANT(matcher::route_ab_noexact)
RB_TEST_VARIANT(matcher::route_ab_bytes)
RB_TEST_VARIANT(matcher::route_ab_heapstack)
RB_TEST_VARIANT(matcher::route_ab_strings)
#undef RB_TEST_VARIANT

enum class Expect { SameTable, NoHashed, AllHashed, NoExact };

template <class View>
void check(const char* name, Expect what, const rb::Table& t, const rb::Ring& r,
           const matcher::route::RuntimeTable& pinned, const std::string& tid) {
    using V = Variant<View>;
    std::vector<std::string> patterns;
    const auto specs = specs_of<typename V::Spec>(t, patterns);
    const auto table = V::build(specs);
    const std::string where = std::string(name) + " " + tid;
    expect(V::ok(table), where + ": the table builds");
    if (!V::ok(table)) {
        return;
    }
    const View v = table.view();
    const matcher::route::TableView p = pinned.view();
    switch (what) {
        case Expect::SameTable:
            expect(same_table(p, v), where + ": the table is the pinned code's");
            break;
        case Expect::NoHashed:
            expect(hashed_nodes(v) == 0, where + ": a node is hashed");
            expect(nodes_with_edges(v) >= nodes_with_edges(p), where + ": a node lost its edges");
            break;
        case Expect::AllHashed:
            expect(hashed_nodes(v) == nodes_with_edges(v), where + ": a node with an edge is linear");
            break;
        case Expect::NoExact:
            expect(v.literals.empty() && v.literal_methods == 0, where + ": the exact-match table is not empty");
            break;
    }
    for (std::size_t i = 0; i < r.queries.size(); ++i) {
        const rb::Query& q = r.queries[i];
        for (unsigned m = 0; m <= rb::kMethods; ++m) {
            const unsigned method = m == rb::kMethods ? static_cast<unsigned>(q.method) : m;
            same_answer(matcher::route::find(p, method, q.path), V::find(v, method, q.path), q.path,
                        where + " query " + std::to_string(i) + " method " + std::to_string(method));
        }
    }
}

}  // namespace

int main() {
    const rb::Shape shapes[] = {rb::Shape::Static, rb::Shape::ParamLast, rb::Shape::ParamFirst, rb::Shape::Rest,
                                rb::Shape::Wild, rb::Shape::MixedDisjoint, rb::Shape::MixedOverlap};
    std::size_t tables = 0;
    std::size_t pinned_hashed = 0;
    std::size_t pinned_literal = 0;
    for (const rb::Shape shape : shapes) {
        for (const std::uint32_t m : {10u, 100u, 1000u, 10000u}) {
            for (const std::uint64_t seed : {1u, 2u}) {
                for (const std::uint8_t methods : {std::uint8_t{1}, std::uint8_t{3}}) {
                    rb::Table t;
                    try {
                        t = rb::generate_table({shape, m, seed, methods, false});
                    } catch (const std::invalid_argument&) {
                        continue;  // the shape cannot hold m distinct routes
                    }
                    const rb::Ring r = rb::generate_ring(t, {512, seed + 1, 200, 0.0, true});
                    const std::string tid = std::string(rb::shape_name(shape)) + " m=" + std::to_string(m) +
                                            " seed=" + std::to_string(seed) + " methods=" + std::to_string(methods);
                    std::vector<std::string> patterns;
                    const auto specs = specs_of<matcher::route::RouteSpec>(t, patterns);
                    const matcher::route::RuntimeTable pinned = matcher::route::make_runtime_table(specs);
                    expect(pinned.error == matcher::route::BuildError::None, "pinned " + tid + ": the table builds");
                    if (pinned.error != matcher::route::BuildError::None) {
                        continue;
                    }
                    ++tables;
                    pinned_hashed += hashed_nodes(pinned.view());
                    pinned_literal += pinned.view().literals.size();
                    check<matcher::route_copy::TableView>("copy", Expect::SameTable, t, r, pinned, tid);
                    check<matcher::route_ab_bytes::TableView>("ab-bytes", Expect::SameTable, t, r, pinned, tid);
                    check<matcher::route_ab_linear::TableView>("ab-linear", Expect::NoHashed, t, r, pinned, tid);
                    check<matcher::route_ab_hashed::TableView>("ab-hashed", Expect::AllHashed, t, r, pinned, tid);
                    check<matcher::route_ab_noexact::TableView>("ab-noexact", Expect::NoExact, t, r, pinned, tid);
                    check<matcher::route_ab_heapstack::TableView>("ab-heapstack", Expect::SameTable, t, r, pinned, tid);
                    check<matcher::route_ab_strings::TableView>("ab-strings", Expect::SameTable, t, r, pinned, tid);
                }
            }
        }
    }
    // The tables must reach what the changes remove, or the checks above would pass vacuously.
    expect(tables == 7 * 4 * 2 * 2, "not every planned table was built: " + std::to_string(tables));
    expect(pinned_hashed > 0, "no pinned table has a hashed node");
    expect(pinned_literal > 0, "no pinned table has an exact-match table");
    expect(compared > 0, "no lookup was compared");
    expect(not_found > 0, "no compared lookup reached a 404");
    expect(not_allowed > 0, "no compared lookup reached a 405");
    expect(with_captures > 0, "no compared lookup reached an answer with captures");
    std::printf("test_ablation: the pinned answers reached %llu 404, %llu 405 and %llu answers with captures\n",
                static_cast<unsigned long long>(not_found), static_cast<unsigned long long>(not_allowed),
                static_cast<unsigned long long>(with_captures));
    std::printf("test_ablation: %s (%zu tables, %llu lookups compared, %d failing)\n", failures ? "FAILED" : "ok", tables,
                static_cast<unsigned long long>(compared), failures);
    return failures ? 1 : 0;
}
