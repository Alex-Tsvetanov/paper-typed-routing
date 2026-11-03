// The adversarial tool's tables, queries, expected answers and checks (tools/adversarial.hpp).
#include <set>
#include <string>
#include <vector>

#include "core/table.hpp"
#include "tools/adversarial.hpp"

namespace adv {
namespace {

std::string literal_of(Family f) { return f == Family::Two ? "a" : "1"; }

// The k segments every query of a table starts with, without the leading '/'.
std::string prefix(const TableSpec& s) {
    std::string p;
    for (unsigned i = 0; i < s.depth; ++i) {
        p += (i ? "/" : "") + literal_of(s.family);
    }
    return p;
}

}  // namespace

std::string family_name(Family f) { return f == Family::Two ? "two-kinds" : "four-kinds"; }

std::string query_name(Query q) {
    switch (q) {
        case Query::Miss: return "miss";
        case Query::LastHit: return "last-hit";
        case Query::OtherMethod: return "other-method";
    }
    return "?";
}

std::string table_id(const TableSpec& s) {
    return std::string(s.family == Family::Two ? "two" : "four") + "-k" + std::to_string(s.depth) +
           (s.catch_all ? "-catch-all" : "");
}

std::vector<unsigned> depths(Family f) {
    return f == Family::Two ? std::vector<unsigned>{1, 2, 4, 8, 12, 16} : std::vector<unsigned>{1, 2, 4, 6, 8};
}

std::vector<TableSpec> table_specs() {
    std::vector<TableSpec> out;
    for (const Family f : {Family::Two, Family::Four}) {
        for (const unsigned k : depths(f)) {
            out.push_back({f, k, false});
            out.push_back({f, k, true});
        }
    }
    return out;
}

std::vector<Cell> cells() {
    std::vector<Cell> out;
    for (const TableSpec& s : table_specs()) {
        for (const Query q : kQueries) {
            if (!s.catch_all || q == Query::Miss) {
                out.push_back({table_id(s) + "-" + query_name(q), s, q});
            }
        }
    }
    return out;
}

Table make_table(const TableSpec& s) {
    Table t;
    t.spec = s;
    const unsigned kinds = s.family == Family::Two ? 2 : 4;
    std::uint64_t n = 1;
    for (unsigned i = 0; i < s.depth; ++i) {
        n *= kinds;
    }
    std::string text;
    for (const unsigned m : {kGet, kPut}) {
        for (std::uint64_t c = 0; c < n; ++c) {
            // Segment i takes digit i of c in base `kinds`, the first segment the most significant:
            // 0 the literal, then (four-kinds) u64 and i64, and last the plain parameter.
            std::vector<unsigned> digit(s.depth);
            std::uint64_t x = c;
            for (unsigned i = s.depth; i-- > 0; x /= kinds) {
                digit[i] = static_cast<unsigned>(x % kinds);
            }
            std::string p;
            for (unsigned i = 0; i < s.depth; ++i) {
                const unsigned d = digit[i];
                const std::string name = "p" + std::to_string(i);
                p += '/';
                if (d == 0) {
                    p += literal_of(s.family);
                } else if (d == kinds - 1) {
                    p += '{' + name + '}';
                } else {
                    p += '{' + name + (d == 1 ? ":u64}" : ":i64}");
                }
            }
            p += c + 1 == n ? "/all" : "/end";
            if (m == kGet && c + 1 == n) {
                t.all_param = static_cast<std::uint32_t>(t.patterns.size());
            }
            t.patterns.push_back(p);
            t.methods.push_back(m);
        }
        if (s.catch_all) {
            if (m == kGet) {
                t.catch_all = static_cast<std::uint32_t>(t.patterns.size());
            }
            t.patterns.push_back("/{*rest}");
            t.methods.push_back(m);
        }
    }
    for (std::size_t i = 0; i < t.patterns.size(); ++i) {
        text += std::to_string(t.methods[i]) + ' ' + t.patterns[i] + '\n';
    }
    t.digest = rb::sha256_hex(text);
    return t;
}

Request request(const Table& t, Query q) {
    const std::string p = '/' + prefix(t.spec);
    switch (q) {
        case Query::Miss: return {kGet, p + "/miss"};
        case Query::LastHit: return {kGet, p + "/all"};
        case Query::OtherMethod: return {kDelete, p + "/miss"};
    }
    return {};
}

Answer expected(const Table& t, Query q) {
    const Request r = request(t, q);
    Answer a;
    switch (q) {
        case Query::Miss:
            if (t.spec.catch_all) {
                a = {0, t.catch_all, 0, {r.path.substr(1)}};
            }
            break;
        case Query::LastHit:
            a = {0, t.all_param, 0, std::vector<std::string>(t.spec.depth, literal_of(t.spec.family))};
            break;
        case Query::OtherMethod:
            if (t.spec.catch_all) {
                a = {1, kNone, static_cast<std::uint16_t>((1u << kGet) | (1u << kPut)), {}};
            }
            break;
    }
    return a;
}

std::uint32_t expected_walks(const Table& t, Query q) {
    if (expected(t, q).status == 0) {
        return 1;
    }
    return static_cast<std::uint32_t>(std::set<unsigned>(t.methods.begin(), t.methods.end()).size());
}

const char* first_difference(const Image& a, const Image& b) {
    if (a.nodes != b.nodes) {
        return "nodes";
    }
    if (a.edges != b.edges) {
        return "edges";
    }
    if (a.literals != b.literals) {
        return "literals";
    }
    if (a.arena != b.arena) {
        return "arena";
    }
    return a == b ? nullptr : "roots or method masks";
}

std::string answer_text(const Answer& a) {
    if (a.status == 0) {
        return std::to_string(a.route);
    }
    return a.status == 1 ? "405" : "404";
}

Check check(const Answer& want, const Answer& pinned, const Answer& copy, const Counts& c, std::uint32_t walks) {
    Check k;
    k.expected_answer = pinned == want;
    k.same_answer = copy == pinned;
    k.bound_entries = c.each_walk_within && c.entries <= c.walked_nodes;
    k.bound_resumptions = c.max_resumptions <= kMaxResumptions;
    // The bounds above are "at most": zero satisfies them, so a count that saw nothing must fail here.
    k.counted = c.entries >= 1;
    k.pops_resume = c.resumptions == c.popped && c.popped <= c.pushed;
    k.entered_once = c.max_entries <= 1;
    k.walks_as_expected = walks >= 1 && c.walks == walks;
    return k;
}

int self_test(std::FILE* out) {
    int failures = 0;
    int queries = 0;
    for (const TableSpec& s : table_specs()) {
        const Table t = make_table(s);
        const Pinned pinned(t);
        Counting counting(t);
        if (!pinned.ok() || !counting.ok()) {
            std::fprintf(out, "%s: FAIL: a table does not build (pinned %s, copy %s)\n", table_id(s).c_str(),
                         pinned.ok() ? "ok" : "failed", counting.ok() ? "ok" : "failed");
            ++failures;
            continue;
        }
        if (const char* part = first_difference(pinned.image(), counting.image())) {
            std::fprintf(out, "%s: FAIL: the tables do not build alike, byte for byte (%s differ; pinned %zu nodes, "
                              "copy %zu)\n", table_id(s).c_str(), part, pinned.nodes(), counting.nodes());
            ++failures;
            continue;
        }
        for (const Query q : kQueries) {
            const Request r = request(t, q);
            Counts c;
            const Answer a = pinned.find(r);
            const Answer b = counting.find(r, c);
            const std::uint32_t walks = expected_walks(t, q);
            const Check k = check(expected(t, q), a, b, c, walks);
            ++queries;
            failures += !k.ok();
            std::fprintf(out,
                         "%s %s: answer %s (expected %s, copy %s); entries %llu of %llu nodes walked in %u walks "
                         "(expected %u); max resumptions %u of %u; backtracks %llu; deepest stack %u: %s\n",
                         table_id(s).c_str(), query_name(q).c_str(), answer_text(a).c_str(),
                         k.expected_answer ? "yes" : "NO", k.same_answer ? "same" : "DIFFERS",
                         static_cast<unsigned long long>(c.entries), static_cast<unsigned long long>(c.walked_nodes),
                         c.walks, walks, c.max_resumptions, kMaxResumptions,
                         static_cast<unsigned long long>(c.popped), c.deepest, k.ok() ? "ok" : "FAIL");
        }
    }
    std::fprintf(out, "self-test: %d queries on %zu tables, %d failing\n", queries, table_specs().size(), failures);
    return failures;
}

}  // namespace adv
