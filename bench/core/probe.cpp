#include "core/probe.hpp"

#include <exception>

#include "core/json.hpp"

// The rules are the path semantics of design/router-v2.md: raw bytes, a parameter over one
// non-empty segment, a catch-all over a non-empty remainder taken as sent, a strict trailing
// slash, the most specific route first whatever the registration order, and 405 when only
// another method's routes match.
namespace rb {
namespace {

struct Want {
    Method method;
    std::string path;
    RouteId id;
    std::vector<std::string> caps;
};

struct Case {
    std::string name;
    std::string rule;
    std::vector<std::pair<Method, std::string>> routes;
    std::vector<Want> queries;
};

constexpr Method G = Method::Get;
constexpr Method P = Method::Post;
constexpr Method U = Method::Put;
constexpr Method D = Method::Delete;

std::vector<Case> cases() {
    std::vector<Case> out;
    const std::string specific = "the most specific route wins, in either registration order";
    out.push_back({"static-then-param", specific, {{G, "/a/b"}, {G, "/a/{x}"}},
                   {{G, "/a/b", 0, {}}, {G, "/a/c", 1, {"c"}}}});
    out.push_back({"param-then-static", specific, {{G, "/a/{x}"}, {G, "/a/b"}},
                   {{G, "/a/b", 1, {}}, {G, "/a/c", 0, {"c"}}}});

    // RFC 3986, section 3.3: segment = *pchar, and pchar = unreserved / pct-encoded /
    // sub-delims / ":" / "@". Each of these is a legal parameter value, taken as sent.
    Case pchar{"pchar", "RFC 3986 section 3.3: every pchar is legal in a segment and is taken as sent",
               {{G, "/u/{x}"}}, {}};
    for (const char* v : {"a-b", "a.b", "a_b", "a~b", "a!b", "a$b", "a&b", "a'b", "a(b)", "a*b", "a+b", "a,b",
                          "a;b", "a=b", "a:b", "a@b", "a%20b", "a%2Fb"}) {
        pchar.queries.push_back({G, std::string("/u/") + v, 0, {v}});
    }
    out.push_back(std::move(pchar));

    out.push_back({"raw-bytes", "bytes are compared as sent: no percent-decoding, no case folding of escapes",
                   {{G, "/caf%C3%A9"}},
                   {{G, "/caf%C3%A9", 0, {}}, {G, "/caf%c3%a9", kNoRoute, {}}}});
    out.push_back({"catch-all", "a catch-all matches a non-empty remainder, taken as sent", {{G, "/f/{*p}"}},
                   {{G, "/f/a", 0, {"a"}},
                    {G, "/f/a/b/c", 0, {"a/b/c"}},
                    {G, "/f/a/", 0, {"a/"}},
                    {G, "/f", kNoRoute, {}},
                    {G, "/f/", kNoRoute, {}}}});
    out.push_back({"empty-segment", "a parameter matches one non-empty segment", {{G, "/u/{x}"}},
                   {{G, "/u/", kNoRoute, {}}, {G, "/u//", kNoRoute, {}}}});
    out.push_back({"trailing-slash", "a trailing slash is strict", {{G, "/a/b"}, {G, "/c/{x}"}},
                   {{G, "/a/b", 0, {}}, {G, "/a/b/", kNoRoute, {}}, {G, "/c/x/", kNoRoute, {}}}});
    out.push_back({"method", "the request's method first; 405 when only another method's routes match",
                   {{G, "/a/b"}, {P, "/a/{x}"}, {G, "/p/{x}"}, {U, "/p/{x}"}},
                   {{G, "/a/b", 0, {}},
                    {P, "/a/b", 1, {"b"}},
                    {D, "/a/b", kMethodNotAllowed, {}},
                    {P, "/p/q", kMethodNotAllowed, {}},
                    {D, "/zz", kNoRoute, {}}}});
    return out;
}

std::string id_text(RouteId id) {
    if (id == kNoRoute) {
        return "404";
    }
    return id == kMethodNotAllowed ? "405" : std::to_string(id);
}

}  // namespace

std::vector<std::string> run_probes(Runner& arm) {
    std::vector<std::string> lines;
    const ArmInfo info = arm.describe();
    for (const Case& c : cases()) {
        std::vector<Route> routes;
        std::vector<std::string> texts;
        for (const auto& [method, text] : c.routes) {
            routes.push_back(parse_route(method, text));
            texts.push_back(std::string(method_name(method)) + " " + text);
        }
        std::string refused;
        try {
            arm.build(routes);
        } catch (const Refused& e) {
            refused = e.what();
        } catch (const std::exception& e) {
            refused = std::string("exception: ") + e.what();
        }
        for (const Want& w : c.queries) {
            Json j;
            j.str("arm", info.name).str("version", info.version).str("case", c.name).str("rule", c.rule);
            j.strs("routes", texts).str("method", method_name(w.method)).str("path", w.path);
            j.str("want_id", id_text(w.id)).strs("want_caps", w.caps);
            if (!refused.empty()) {
                j.str("status", "refused").str("reason", refused);
            } else {
                std::vector<std::string> got;
                RouteId id = kNoRoute;
                std::string error;
                try {
                    id = arm.lookup(w.method, w.path, got);
                } catch (const std::exception& e) {
                    error = e.what();
                }
                if (!error.empty()) {
                    j.str("status", "exception").str("reason", error);
                } else {
                    // A catch-all value may come back with its leading '/' (httprouter keeps
                    // it), as in the agreement test.
                    const bool rest = id < routes.size() && !routes[id].segs.empty() &&
                                      routes[id].segs.back().kind == Seg::Rest;
                    if (rest && !got.empty() && w.caps.size() == got.size() && got.back().size() > 1 &&
                        got.back().front() == '/' && got.back().substr(1) == w.caps.back()) {
                        got.back().erase(0, 1);
                    }
                    const bool found = id != kNoRoute && id != kMethodNotAllowed;
                    const bool pass = id == w.id && (!found || got == w.caps);
                    j.str("got_id", id_text(id)).strs("got_caps", got).str("status", pass ? "pass" : "fail");
                }
            }
            lines.push_back(j.done());
        }
    }
    return lines;
}

}  // namespace rb
