// test_adversarial: the adversarial tool's tests (ctest).
// 1. Every count of every query of every table equals its closed form, derived from the walk's code
//    (lookup.hpp, detail::walk) and the tables' shape. With b kinds of child per node above depth k
//    (b = 2 or 4) the trie of one method has I = (b^(k+1) - 1) / (b - 1) nodes at depths 0 to k, b^k
//    last literals and, with the catch-all, one more node. A node above depth k pushes a choice point
//    for every kind but the plain parameter (b - 1 pushes); the root with the catch-all pushes once
//    more, when it takes its parameter. Then:
//      miss          with the catch-all, one walk: entries I, pushed and popped b^k (GET's walk ends
//                    in the catch-all); without it, GET's walk finds nothing and the 405 test walks
//                    PUT's trie too: two walks, each with entries I, pushed and popped b^k - 1
//      last-hit      one walk; entries I + 1; pushed b^k - 1 + c, popped b^k - 1 (the root's last
//                    choice is still on the stack when the route matches)
//      other-method  two walks (GET's and PUT's tries, for 405), each a miss
//    where c is 1 with the catch-all and 0 without; the deepest stack is k; every pop resumes a
//    node, the most resumptions of one node are b - 1 + c (b - 1 on last-hit), and no node is
//    entered twice. The walks a query must make (expected_walks) are those above, and the real
//    counts of every query pass every check.
// 2. The self-test passes (adversarial self-test runs the same function).
// 3. The checks fail where they must: one entry over the nodes walked, a walk over its own trie, five
//    resumptions of a node, an answer that differs, and a count that saw nothing or counts wrongly
//    (all zero; no entry; a pop that is not a resumption; more pops than pushes; a node entered
//    twice; a walk too many or too few). The real counts of a query, zeroed as a deleted hook would
//    leave them, fail.
// 4. The cells are the plan's 44, with unique ids, and the tables keep v2's limits.
// 5. A table that does not build counts nothing and answers like an empty one, in both codes, and the
//    check fails on it; the two builds' images are equal, and differ after one byte changes.
#include <cstdint>
#include <cstdio>
#include <set>
#include <string>
#include <vector>

#include "tools/adversarial.hpp"

namespace {

int failures = 0;

void expect(bool ok, const std::string& what) {
    if (!ok) {
        ++failures;
        std::printf("FAIL: %s\n", what.c_str());
    }
}

std::uint64_t power(std::uint64_t b, unsigned k) {
    std::uint64_t p = 1;
    for (unsigned i = 0; i < k; ++i) {
        p *= b;
    }
    return p;
}

void closed_forms() {
    for (const adv::TableSpec& s : adv::table_specs()) {
        const adv::Table t = adv::make_table(s);
        const adv::Pinned pinned(t);
        adv::Counting counting(t);
        const std::uint64_t b = s.family == adv::Family::Two ? 2 : 4;
        const unsigned k = s.depth;
        const std::uint64_t c = s.catch_all ? 1 : 0;
        const std::uint64_t inner = (power(b, k + 1) - 1) / (b - 1);
        const std::uint64_t trie = inner + power(b, k) + c;
        const std::string tid = adv::table_id(s);
        expect(counting.ok(), tid + ": the copy builds");
        expect(counting.trie_nodes(adv::kGet) == trie && counting.trie_nodes(adv::kPut) == trie,
               tid + ": trie nodes " + std::to_string(counting.trie_nodes(adv::kGet)) + ", want " +
                   std::to_string(trie));
        expect(counting.trie_nodes(adv::kDelete) == 0, tid + ": no trie for DELETE");
        expect(t.patterns.size() == 2 * (power(b, k) + c), tid + ": routes");
        for (const adv::Query q : adv::kQueries) {
            adv::Counts n;
            const adv::Answer counted = counting.find(adv::request(t, q), n);
            const std::string w = tid + " " + adv::query_name(q) + ": ";
            const std::uint64_t walks = q == adv::Query::OtherMethod || (q == adv::Query::Miss && c == 0) ? 2 : 1;
            const std::uint64_t pushed = walks * (power(b, k) - 1 + c);
            const std::uint64_t popped = q == adv::Query::LastHit ? power(b, k) - 1 : pushed;
            const std::uint64_t entries = walks * inner + (q == adv::Query::LastHit ? 1 : 0);
            const std::uint32_t most = static_cast<std::uint32_t>(b - 1 + (q == adv::Query::LastHit ? 0 : c));
            expect(adv::expected_walks(t, q) == walks,
                   w + "expected walks " + std::to_string(adv::expected_walks(t, q)) + ", want " +
                       std::to_string(walks));
            expect(n.walks == walks, w + "walks " + std::to_string(n.walks));
            expect(n.walked_nodes == walks * trie, w + "walked nodes " + std::to_string(n.walked_nodes));
            expect(n.entries == entries,
                   w + "entries " + std::to_string(n.entries) + ", want " + std::to_string(entries));
            expect(n.pushed == pushed, w + "pushed " + std::to_string(n.pushed) + ", want " + std::to_string(pushed));
            expect(n.popped == popped, w + "popped " + std::to_string(n.popped) + ", want " + std::to_string(popped));
            expect(n.resumptions == n.popped, w + "resumptions equal pops");
            expect(n.deepest == k, w + "deepest stack " + std::to_string(n.deepest));
            expect(n.max_entries == 1, w + "a node entered twice");
            expect(n.max_resumptions == most, w + "most resumptions " + std::to_string(n.max_resumptions) +
                                                  ", want " + std::to_string(most));
            expect(n.each_walk_within, w + "a walk entered more nodes than its trie has");
            expect(adv::check(adv::expected(t, q), pinned.find(adv::request(t, q)), counted, n,
                              adv::expected_walks(t, q)).ok(),
                   w + "the real counts pass every check");
        }
    }
}

// Counts that satisfy every check of a query that walks one trie of 7 nodes and backtracks twice.
adv::Counts good_counts() {
    adv::Counts c;
    c.entries = 7;
    c.walked_nodes = 7;
    c.resumptions = 2;
    c.pushed = 2;
    c.popped = 2;
    c.deepest = 2;
    c.max_entries = 1;
    c.max_resumptions = 4;
    c.walks = 1;
    return c;
}

void checks_fail() {
    const adv::Counts ok = good_counts();
    const adv::Answer a{2, adv::kNone, 0, {}};
    expect(adv::check(a, a, a, ok, 1).ok(), "check: entries equal to the nodes walked and 4 resumptions pass");
    adv::Counts over = ok;
    over.entries = 8;
    expect(!adv::check(a, a, a, over, 1).bound_entries, "check: one entry over the nodes walked fails");
    adv::Counts walk = ok;
    walk.each_walk_within = false;
    expect(!adv::check(a, a, a, walk, 1).bound_entries, "check: a walk over its own trie fails");
    adv::Counts res = ok;
    res.max_resumptions = 5;
    expect(!adv::check(a, a, a, res, 1).bound_resumptions, "check: five resumptions of a node fail");
    const adv::Answer b{0, 3, 0, {"a"}};
    expect(!adv::check(a, a, b, ok, 1).same_answer, "check: a copy that answers otherwise fails");
    expect(!adv::check(b, a, a, ok, 1).expected_answer, "check: a pinned answer other than the expected one fails");

    // A count that saw nothing satisfies every "at most", so each of these fails on a check of its own.
    const adv::Check zero = adv::check(a, a, a, adv::Counts{}, 1);
    expect(!zero.ok() && !zero.counted && !zero.walks_as_expected, "check: an all-zero count fails");
    adv::Counts none = ok;
    none.entries = 0;
    expect(!adv::check(a, a, a, none, 1).counted, "check: no entry counted fails");
    adv::Counts silent = ok;
    silent.resumptions = 0;
    expect(!adv::check(a, a, a, silent, 1).pops_resume, "check: a pop that is not a resumption fails");
    adv::Counts extra = ok;
    extra.resumptions = 3;
    expect(!adv::check(a, a, a, extra, 1).pops_resume, "check: a resumption that is not a pop fails");
    adv::Counts pops = ok;
    pops.popped = 3;
    pops.resumptions = 3;
    expect(!adv::check(a, a, a, pops, 1).pops_resume, "check: more pops than pushes fails");
    adv::Counts twice = ok;
    twice.max_entries = 2;
    expect(!adv::check(a, a, a, twice, 1).entered_once, "check: a node entered twice in a walk fails");
    expect(!adv::check(a, a, a, ok, 2).walks_as_expected, "check: one walk too few fails");
    adv::Counts many = ok;
    many.walks = 3;
    expect(!adv::check(a, a, a, many, 2).walks_as_expected, "check: one walk too many fails");
    expect(!adv::check(a, a, a, ok, 0).walks_as_expected, "check: no walk expected is not a pass");
}

// The real counts of a query pass; the same counts with a hook's effect removed fail.
void broken_counts_fail() {
    const adv::TableSpec specs[] = {{adv::Family::Two, 2, false}, {adv::Family::Two, 4, true},
                                    {adv::Family::Four, 2, false}};
    for (const adv::TableSpec& s : specs) {
        const adv::Table t = adv::make_table(s);
        const adv::Pinned pinned(t);
        adv::Counting counting(t);
        for (const adv::Query q : adv::kQueries) {
            const adv::Request r = adv::request(t, q);
            adv::Counts n;
            const adv::Answer counted = counting.find(r, n);
            const adv::Answer a = pinned.find(r);
            const adv::Answer want = adv::expected(t, q);
            const std::string w = adv::table_id(s) + " " + adv::query_name(q) + ": ";
            const std::uint32_t walks = adv::expected_walks(t, q);
            expect(adv::check(want, a, counted, n, walks).ok(), w + "the real counts pass");
            expect(n.popped > 0 && n.pushed > 0, w + "the query backtracks, so a missing pop shows");

            adv::Counts no_visits = n;  // the visit hook deleted: no entry, no resumption
            no_visits.entries = 0;
            no_visits.resumptions = 0;
            no_visits.max_entries = 0;
            no_visits.max_resumptions = 0;
            expect(!adv::check(want, a, counted, no_visits, walks).ok(), w + "no visits fails");
            expect(!adv::check(want, a, counted, adv::Counts{}, walks).ok(), w + "all zero fails");
            adv::Counts no_walks = n;  // the walk hook deleted
            no_walks.walks = 0;
            no_walks.walked_nodes = 0;
            expect(!adv::check(want, a, counted, no_walks, walks).ok(), w + "no walks fails");
            adv::Counts no_pops = n;  // the pop hook deleted
            no_pops.popped = 0;
            expect(!adv::check(want, a, counted, no_pops, walks).ok(), w + "no pops fails");
            adv::Counts no_pushes = n;  // the push hook deleted
            no_pushes.pushed = 0;
            expect(!adv::check(want, a, counted, no_pushes, walks).ok(), w + "no pushes fails");
        }
    }
}

// A table that does not build: the copy counts nothing, neither code answers, and the check fails.
void failed_build() {
    adv::Table t = adv::make_table({adv::Family::Two, 1, false});
    t.patterns = {"/a", "/a"};  // a duplicate route does not build
    t.methods = {adv::kGet, adv::kGet};
    const adv::Pinned pinned(t);
    adv::Counting counting(t);
    expect(!pinned.ok() && !counting.ok(), "a duplicate route does not build in either code");
    const adv::Request r{adv::kGet, "/a"};
    adv::Counts n;
    n.entries = 99;  // find must reset what it was given
    const adv::Answer counted = counting.find(r, n);
    expect(n.entries == 0 && n.walks == 0 && n.popped == 0, "a failed build counts nothing");
    expect(counted == adv::Answer{} && pinned.find(r) == adv::Answer{}, "a failed build answers like an empty table");
    expect(!adv::check(adv::Answer{}, pinned.find(r), counted, n, 1).ok(), "the check fails on a failed build");
}

// The two builds are equal byte for byte, and one changed byte is found.
void images() {
    const adv::Table t = adv::make_table({adv::Family::Four, 2, true});
    const adv::Pinned pinned(t);
    const adv::Counting counting(t);
    const adv::Image p = pinned.image();
    adv::Image c = counting.image();
    expect(!p.nodes.empty() && !p.edges.empty() && !p.arena.empty(), "the images hold nodes, edges and an arena");
    expect(p == c && adv::first_difference(p, c) == nullptr, "the pinned build and the copy's are equal");
    for (std::vector<unsigned char>* part : {&c.nodes, &c.edges, &c.literals, &c.arena}) {
        if (part->empty()) {
            continue;
        }
        part->back() ^= 1;
        expect(!(p == c) && adv::first_difference(p, c) != nullptr, "a changed byte is found");
        part->back() ^= 1;
    }
    expect(p == c, "the images are equal again after the bytes are restored");
    c.arena.pop_back();
    expect(adv::first_difference(p, c) != nullptr, "an arena one byte short is found");
}

void cells() {
    const auto all = adv::cells();
    expect(all.size() == 44, "44 cells, not " + std::to_string(all.size()));
    std::set<std::string> ids;
    for (const adv::Cell& c : all) {
        ids.insert(c.id);
    }
    expect(ids.size() == all.size(), "cell ids are unique");
    expect(adv::table_specs().size() == 22, "22 tables");
    for (const adv::TableSpec& s : adv::table_specs()) {
        expect(s.depth + 1 <= 32 && s.depth <= 16, adv::table_id(s) + ": within v2's 32 segments and 16 parameters");
    }
}

}  // namespace

int main() {
    closed_forms();
    checks_fail();
    broken_counts_fail();
    failed_build();
    images();
    cells();
    const int self = adv::self_test(stdout);
    expect(self == 0, "the self-test passes");
    std::printf("test_adversarial: %s (%d failing)\n", failures == 0 ? "ok" : "FAILED", failures);
    return failures == 0 ? 0 : 1;
}
