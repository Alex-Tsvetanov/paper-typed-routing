// Deterministic route tables and query rings.
//
// A table of the first five shapes has one layout: every route has the same number of
// segments and the same kind of segment at each position, so two routes differ only in their
// literals. The literal tuples are drawn without repetition, which makes every query path
// match exactly one route in every arm; the arms can then be compared on the same result.
// The mixed and github tables have more than one layout; a query's expected route is the
// most specific route that matches it (a literal before a parameter before a catch-all, at
// the first segment where two routes differ), which a general reference matcher finds.
//
//   shape        segments                  example
//   static       /l/l/l                    /tovaru/kelimo/sanide
//   param-last   /l/l/{p0}                 /tovaru/kelimo/{p0}
//   param-first  /{p0}/l/l                 /{p0}/tovaru/kelimo
//   rest         /l/{p0}/l/{p1}            /tovaru/{p0}/kelimo/{p1}
//   wild         /l/l/{*p0}                /tovaru/kelimo/{*p0}
//   mixed-disjoint  groups of four routes: one fully literal route /a/l/l whose first
//                word is one of the first 16 top words, and three parameter routes of one
//                resource under the other 16: /b/r/{p0}, /b/r/{p0}/s, /b/r/{p0}/s/{p1}.
//                A quarter of the queries target a fully literal route, under first words
//                no parameter route has. No literal stands beside a parameter at one
//                position, so httprouter holds the table.
//   mixed-overlap  groups of four routes of one resource that overlap by precedence, in
//                this order: /t/r/s1, /t/r/{p0} (a parameter beside that literal),
//                /t/r/s1/{p0}, and /t/{p0}/s2/{p1} (a parameter beside the literal r). Half
//                of the queries for the last route carry r as the value of {p0}: a lookup
//                then descends the literal r, fails below it, and backtracks to the
//                parameter. Routes overlap only inside a group (s1 is never an s2 of the
//                same top word), and there the more specific one is registered first, as
//                routers that take the first match ask; routers with precedence ignore the
//                order. httprouter refuses these tables.
//   github       the 203 routes of the GitHub API list of go-http-routing-benchmark
//                (core/github_api.cpp), four methods; m is fixed at 203 and the methods
//                are the list's own (an exploratory real-world cell, not in the H1 grid)
//
// Literals are pseudo-words of 3 to 10 lower-case letters. The first literal of a route is
// drawn from 32 words and every later literal from 4096, so tables share a few top-level
// prefixes and branch widely below them, as REST APIs do. An exploratory vocabulary of long
// words (12 to 24 letters) tests whether a lookup that keys on a segment's first 8 bytes is
// favoured by short literals.
#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "core/route.hpp"

namespace rb {

enum class Shape : std::uint8_t { Static, ParamLast, ParamFirst, Rest, Wild, MixedDisjoint, MixedOverlap, Github };
// The shapes of the H1 grid. Github is apart: one exploratory real-world cell.
inline constexpr Shape kShapes[] = {Shape::Static,        Shape::ParamLast,   Shape::ParamFirst, Shape::Rest,
                                    Shape::Wild,          Shape::MixedDisjoint, Shape::MixedOverlap};
inline constexpr std::uint32_t kGithubRoutes = 203;
const std::vector<std::pair<Method, std::string_view>>& github_api_routes();

std::string_view shape_name(Shape s);
bool parse_shape(std::string_view text, Shape& out);

struct TableSpec {
    Shape shape = Shape::Static;
    std::uint32_t m = 0;       // number of routes
    std::uint64_t seed = 1;
    std::uint8_t methods = 1;  // route i gets method i mod methods (GET, POST, ...)
    bool long_words = false;   // the exploratory vocabulary of 12 to 24 letters
};

struct Table {
    TableSpec spec;
    std::vector<Route> routes;  // registration order; RouteId is the index
    std::string digest;         // sha256 of the rendered routes, one per line, in order
    // Per route, a value for its first parameter that equals a literal beside that
    // parameter (mixed-overlap), used by half of the route's queries; empty: none.
    std::vector<std::string> decoy;
};

// Throws std::invalid_argument if the shape cannot hold m distinct routes.
Table generate_table(const TableSpec& spec);

struct RingSpec {
    std::uint32_t size = 4096;
    std::uint64_t seed = 2;
    std::uint32_t miss_permille = 0;  // share of queries that match no route
    double zipf = 0.0;                // 0: routes drawn uniformly; s > 0: Zipf with exponent s
    bool decoys = true;               // false: no query carries a decoy (an exploratory ring)
};

struct Query {
    Method method = Method::Get;
    std::string path;
    RouteId expect = kNoRoute;
    std::vector<std::string> caps;  // expected captured values in order
};

struct Ring {
    RingSpec spec;
    std::vector<Query> queries;
    std::string digest;  // sha256 over the table digest and every query
};

// Queries drawn uniformly over the table's routes, or, with zipf = s > 0, by a Zipf law: the
// routes are ranked in an order drawn from the ring seed, and the route of rank k (from 1)
// is drawn with probability proportional to 1 / k^s. Parameter values are 1 to 12 characters
// from [a-z0-9]; a catch-all value is 1 to 3 such tokens joined by '/'; a route with a decoy
// takes it as its first parameter's value in half of its queries (none with decoys false). Every query's expectation
// is checked against, or on the mixed and github tables taken from, a reference matcher.
Ring generate_ring(const Table& table, const RingSpec& spec);

// How router v2's lookup structure meets a ring (a model of it, not a measurement of it): a
// method whose routes are all literal is an exact-match table; any other method is one
// segment trie, its literal routes included, walked depth first, a literal child before a
// parameter before a catch-all.
//   exact         queries answered by an exact-match table
//   backtracking  queries whose walk leaves a branch it descended because the branch failed
//   pops          such departures over the whole ring (a query may have several)
// On the one-layout shapes both of the last two are 0; mixed-overlap is built to make them
// positive, so a cell can show that its ring exercises the backtracking.
struct RingWalk {
    std::uint32_t exact = 0;
    std::uint32_t backtracking = 0;
    std::uint64_t pops = 0;
};
RingWalk ring_walk(const Table& table, const Ring& ring);

std::string sha256_hex(std::string_view data);

}  // namespace rb
