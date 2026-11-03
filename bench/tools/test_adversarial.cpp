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
//    entered twice.
// 2. The self-test passes (adversarial self-test runs the same function).
// 3. The checks fail where they must: one entry over the nodes walked, a walk over its own trie, five
//    resumptions of a node, an answer that differs.
// 4. The cells are the plan's 44, with unique ids, and the tables keep v2's limits.
#include <cstdint>
#include <cstdio>
#include <set>
#include <string>

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
            counting.find(adv::request(t, q), n);
            const std::string w = tid + " " + adv::query_name(q) + ": ";
            const std::uint64_t walks = q == adv::Query::OtherMethod || (q == adv::Query::Miss && c == 0) ? 2 : 1;
            const std::uint64_t pushed = walks * (power(b, k) - 1 + c);
            const std::uint64_t popped = q == adv::Query::LastHit ? power(b, k) - 1 : pushed;
            const std::uint64_t entries = walks * inner + (q == adv::Query::LastHit ? 1 : 0);
            const std::uint32_t most = static_cast<std::uint32_t>(b - 1 + (q == adv::Query::LastHit ? 0 : c));
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
        }
    }
}

void checks_fail() {
    adv::Counts ok;
    ok.entries = 7;
    ok.walked_nodes = 7;
    ok.max_resumptions = 4;
    const adv::Answer a{2, adv::kNone, 0, {}};
    expect(adv::check(a, a, a, ok).ok(), "check: entries equal to the nodes walked and 4 resumptions pass");
    adv::Counts over = ok;
    over.entries = 8;
    expect(!adv::check(a, a, a, over).bound_entries, "check: one entry over the nodes walked fails");
    adv::Counts walk = ok;
    walk.each_walk_within = false;
    expect(!adv::check(a, a, a, walk).bound_entries, "check: a walk over its own trie fails");
    adv::Counts res = ok;
    res.max_resumptions = 5;
    expect(!adv::check(a, a, a, res).bound_resumptions, "check: five resumptions of a node fail");
    const adv::Answer b{0, 3, 0, {"a"}};
    expect(!adv::check(a, a, b, ok).same_answer, "check: a copy that answers otherwise fails");
    expect(!adv::check(b, a, a, ok).expected_answer, "check: a pinned answer other than the expected one fails");
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
    cells();
    const int self = adv::self_test(stdout);
    expect(self == 0, "the self-test passes");
    std::printf("test_adversarial: %s (%d failing)\n", failures == 0 ? "ok" : "FAILED", failures);
    return failures == 0 ? 0 : 1;
}
