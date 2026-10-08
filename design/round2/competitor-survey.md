# Competitor survey for round 2 (2026-09-30)

A survey of HTTP routers that round 2 could add as competitors. It was done on 2026-09-30 by a
research agent with web reads only (no download, no clone), and its report is kept here
unchanged in substance so that its sources are not lost. **Every fact below, except one, comes
from the agent's reads at the URLs given and was not checked again.** The one fact checked
again, by reading the file directly on 2026-09-30, is axum's matchit dependency (the first
section). Before the pre-specification is frozen, each fact used there is read again at its
URL.

Conventions of the report: stars and licence from `https://api.github.com/repos/OWNER/REPO`,
releases from `.../releases/latest`, Rust releases and downloads from
`https://crates.io/api/v1/crates/NAME`, all read on 2026-09-30; source files read at the pinned
tag unless said otherwise. "Transcription" means copying the lookup code into the harness, as
round 1 did with gin's `tree.go`.

Inclusion rules the survey applied:
1. a router API that can be built and queried without a running server or socket, or a lookup
   that can be transcribed faithfully from source;
2. path parameters with captured values;
3. a pinnable release, and a documented or evident best configuration;
4. evidence of wide use (stars, downloads, being a well-known framework's router) or a
   published state-of-the-art claim;
5. a language the harness reaches: C, C++, Rust (C interface) or Go (cgo); others as related
   work only.

## A correction to round 1's text (checked again)

Round 1 described matchit 0.9.2 as "the router of axum". axum's newest release on crates.io is
0.8.9, released 2026-04-14 (https://crates.io/api/v1/crates/axum). At tag `axum-v0.8.9`,
`axum/Cargo.toml` pins `matchit = "=0.8.4"`
(https://raw.githubusercontent.com/tokio-rs/axum/axum-v0.8.9/axum/Cargo.toml, read again
directly on 2026-09-30: the lines `version = "0.8.9"` and `matchit = "=0.8.4"`). Only axum's
unreleased `main` pins `matchit = "=0.9.2"`
(https://github.com/tokio-rs/axum/blob/main/axum/Cargo.toml).

## C and C++

1. **uWebSockets `HttpRouter`**, https://github.com/uNetworking/uWebSockets. Release v20.80.0,
   2026-09-03 (tags `v21.0.0-alpha1` and `v21.0.0-alpha2` also exist). Apache-2.0, 18,993
   stars. `src/HttpRouter.h`
   (https://github.com/uNetworking/uWebSockets/blob/v20.80.0/src/HttpRouter.h): a segment trie
   with the method as its first level; children ordered static, then `:`, then `*`; depth-first
   lookup with backtracking; `*` takes the rest of the path; parameters are positional; handlers
   carry a priority, and a handler returning false passes the request on (the harness's must
   return true); no typed parameters; at most 100 segments. API `uWS::HttpRouter<USERDATA>::add`,
   `route`, `getParameters`. Rules 1 to 5 pass. Cost low: the header includes standard headers
   and `MoveOnlyFunction.h`.
2. **glaze `route_table`** (C++23), https://github.com/stephenberry/glaze. Release v9.0.0,
   2026-09-24. MIT, 3,043 stars (the whole library's; the router is a recent part, so rule 4
   passes weakly). `include/glaze/net/http_router.hpp`
   (https://github.com/stephenberry/glaze/blob/v9.0.0/include/glaze/net/http_router.hpp): an
   `unordered_map` of fully static paths first, then a segment trie whose nodes have an
   `unordered_map` of static children, one parameter child and one wildcard child; backtracking
   search static, parameter, wildcard; a parameter may carry a check function
   (`param_constraint::validation`), run at the end node, whose failure backtracks; each lookup
   allocates a vector of segments and a map of parameters. API `glz::route_table<H>::match`.
   Rules 1 to 5 pass. Cost low: header-only, "Requires C++23" (README at v9.0.0); the includes
   of `glaze/json/generic.hpp` were not inspected.
3. **cpp-httplib**, https://github.com/yhirose/cpp-httplib. Release v0.58.0, 2026-09-26. MIT,
   16,878 stars. `httplib.h`
   (https://github.com/yhirose/cpp-httplib/blob/v0.58.0/httplib.h): one vector of routes per
   method, searched in order, first match wins (`Server::dispatch_request`); patterns with `/:`
   or without regex characters use `detail::PathParamsMatcher`, others `detail::RegexMatcher`
   (std::regex); so no catch-all without a regular expression, and precedence follows
   registration order. API `httplib::detail::PathParamsMatcher(pattern).match(Request&)`.
   Rules 1 to 5 pass (best configuration evident from `Server::make_matcher`, not documented).
   Cost low (one header).
4. **cinatra** (C++20), https://github.com/qicosmos/cinatra. Release `1.0.0`, 2026-04-29. MIT,
   2,182 stars. Lookup (`include/cinatra/coro_http_connection.hpp`, lines 228 to 290): an exact
   map on "METHOD path", then a radix tree for paths with `:`, then a list of std::regex routes.
   The radix tree (`include/cinatra/coro_radix_tree.hpp`) refuses a literal and a parameter at
   one position, so mixed-depth precedence cannot be expressed. Rules pass; fit partial.
5. **RESTinio express router**, https://github.com/Stiffstream/restinio. Release v0.7.10,
   2026-09-03, 1,305 stars; licence BSD-style text (GitHub reports NOASSERTION). One compiled
   regex per route, searched in order (`dev/restinio/router/express.hpp`), with std, PCRE,
   PCRE2 and Boost regex engines; the documented best engine was not found. Rule 4 weak; cost
   medium to high.
6. **userver** (v3.2, 2026-09-09, Apache-2.0, 2,978 stars): exact paths, then a trie by segment
   position (`core/src/server/http/*.hpp`); internal API only (transcription); catch-all not
   verified; cost high.
7. **Seastar httpd `routes`** (tag `seastar-25.05.0`, commit date 2025-05-26, Apache-2.0, 9,381
   stars): a per-method map of exact URLs, then a list of match rules; public
   `routes::get_handler` (`include/seastar/http/routes.hh`, line 173); cost highest (a full
   Seastar build).
8. **libhv** (v1.3.4, 2025-10-25, BSD-3-Clause, 7,556 stars): `HttpService::GetRoute` loops over
   an `unordered_map` of patterns, first match; precedence follows hash-map order. Not
   recommended.
9. **restbed** (5.0.0, 2026-04-06, AGPL or commercial, 1,998 stars): builds a `std::regex` per
   segment on every request (`service_impl.cpp`, lines 645 and 649). Not recommended.
10. **mongoose** (7.23, 2026-08-12, GPLv2 or commercial, 13,063 stars): a glob matcher
    `mg_match`, no route table. Fails rule 1.
11. Rejected: lithium (no release, rule 3); h2o (prefix match, rule 2; no tagged release since
    2019, rule 3); Beast (no router; its FAQ leaves routing to higher-level code, rules 1 and
    2); POCO (no router, rules 1 and 2).

## Rust

12. **path-tree**, https://github.com/viz-rs/path-tree. Release 0.8.3, 2025-03-23 (0.8.2
    yanked). MIT OR Apache-2.0. 11,795,096 downloads (4,292,663 recent), 135 stars. A
    compressed prefix tree with static and parameter children and backtracking (`src/node.rs`);
    parameter kinds `:name`, `:name?`, `+`, `*`, `**`. API `PathTree::insert` and `find`. Third
    in matchit's published benchmark (below). Rules pass; cost low.
13. **ntex-router** (1.1.0, 2026-09-07, MIT OR Apache-2.0, 666,108 downloads): `Router::recognize`
    walks a segment tree; typed segments through the regex crate. Rules pass.
14. **route-recognizer** (0.3.1, 2021-10-25, MIT, 20,803,596 downloads): NFA-based; no release
    since 2021.
15. **poem** (3.1.12), **salvo_core** (1.0.0), **Rocket** (0.5.1): lookup internal or tied to a
    request type; low value.
16. Rejected: xitca-router (a fork of matchit, rule 4); wayfind (rule 4); gonzales (rules 3 and
    4); axum (it is matchit).

## Go

17. **chi**, https://github.com/go-chi/chi. Release v5.3.2, 2026-08-20. MIT, 22,902 stars. A
    Patricia radix trie with static, regexp, parameter and catch-all nodes (`tree.go`,
    https://github.com/go-chi/chi/blob/v5.3.2/tree.go); public `(*Mux).Find`. Rules pass; cost
    low (cgo).
18. **fiber** (v3.5.0, 2026-08-13, MIT, 40,186 stars): per-method buckets and a linear scan with
    a route parser; typed constraints; lookup unexported (transcription).
19. **echo** (v5.4.0, 2026-09-27, MIT, 32,742 stars): radix tree; lookup needs echo's context.
20. **gorilla/mux** (v1.8.1, 2023-11-05, BSD-3-Clause, 21,838 stars): a regexp per route; repeats
    the regex reference arm.
21. **iris**, **hertz**: transcription only; details not verified.
22. Rejected: fasthttp/router (rule 4, based on httprouter); bunrouter (rule 4, strict reading);
    httptreemux (rule 4, archived).

## Related work only

find-my-way (Fastify's router, JS), Hono (JS), ASP.NET Core's DFA matcher (C#), Envoy's URI
template matcher.

## Papers and benchmark suites (2023 to 2026)

No peer-reviewed paper on HTTP route matching performance from 2023 to 2026 was found.
Benchmark suites, with their own numbers, not measured by this project: matchit's README
(130 routes: matchit first, then gonzales, path-tree, wayfind, route-recognizer, routefinder,
actix, regex); wayfind's CodSpeed suite over seven Rust routers; go-http-routing-benchmark
(last commit 2020-07-26, stale pins); vm-001/gateways-routing-benchmark (route sets of OpenAI,
Okta and GitHub, last push 2024-04-06).

## The survey's ranking

1. uWebSockets `HttpRouter`; 2. glaze `route_table`; 3. chi; 4. path-tree; 5. cpp-httplib.
Next in line: fiber, ntex-router, echo, cinatra.

## Not verified by the survey

RESTinio's documented best engine; userver's catch-all; iris's fall-through; hertz's lineage;
POCO's licence text; the year of IEEE 7280077; the includes of glaze's `json/generic.hpp`.
