// adversarial: RegexMatcher v2's lookup on tables built to make it backtrack, and the written bound
// of its walk checked by counting (design/review-runs/adversarial.md).
//
//   adversarial list
//   adversarial cell --cell ID [--ring N] [--epochs E] [--rep K] [--quick]
//   adversarial self-test
//
// list prints the 44 cells (id, family, depth, catch-all, query), one per line. cell prints one
// JSON object: the cell, the counts of its query from the counting copy (tools/route_count.hpp),
// the checks of tools/adversarial.hpp, and the measurement of rbench's core (core/runner.hpp,
// ArmRunner::measure, unchanged) of v2 at the pinned commit, unmodified, through the regexmatcher-v2
// arm's adapter (arms/rm_arm.hpp, arms/rm_v2.hpp) over a ring of N copies of the query (default
// rbench's 4096). The adapter takes the table from the cell (CellSource), not from rbench's route
// model, which has no typed parameters and stops at 8; so the measurement's table and ring fields
// that describe rbench's generator (shape, table_seed, methods, vocabulary, zipf, decoys, ring_seed,
// miss_permille, ring_exact, ring_backtracking, ring_pops) are placeholders here, and its agreement
// test compares the first 8 captured values (rbench's Captures). The counts and the checks are made
// after the measurement, so the timed process builds and looks up as the arm does and nothing else.
// self-test runs every query of every table through both codes and exits 1 if any check fails.
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <map>
#include <string>
#include <vector>

#include "arms/rm_arm.hpp"
#include "arms/rm_v2.hpp"
#include "core/json.hpp"
#include "core/runner.hpp"
#include "tools/adversarial.hpp"

#ifndef ADV_CODE_COMMIT
#define ADV_CODE_COMMIT "unknown"
#endif
#ifndef RB_REGEXMATCHER_COMMIT
#define RB_REGEXMATCHER_COMMIT "unknown"
#endif
#ifndef RB_BUILD_TYPE
#define RB_BUILD_TYPE "unknown"
#endif
#ifndef RB_SANITIZER
#define RB_SANITIZER ""
#endif

namespace {

using Args = std::map<std::string, std::string>;

// The cell's routes, set before the measurement builds its table from them.
std::vector<matcher::route::RouteSpec> g_specs;

class CellSource {
public:
    void add(const rb::Route&, rb::RouteId) { throw rb::Refused("an adversarial cell is built from its own routes"); }

    template <class L>
    typename L::TableView finalize() {
        table_ = L::build(g_specs);
        if (table_.error != L::kBuildOk) {
            throw rb::Refused("the routes do not build a table");
        }
        return table_.view();
    }

private:
    rb::rm::V2::Built table_;
};

struct Info {
    static rb::ArmInfo info() {
        return {"regexmatcher-v2-adversarial",
                std::string("RegexMatcher v2 ") + std::string(RB_REGEXMATCHER_COMMIT).substr(0, 9) +
                    " (table built at run time, adversarial cells)",
                "views into the path"};
    }
};

using AdversarialArm = rb::rm::Arm<rb::rm::V2, CellSource, Info>;

[[noreturn]] void usage(const char* why) {
    std::fprintf(stderr, "adversarial: %s\nusage: adversarial list | cell --cell ID [--ring N] [--epochs E] [--rep K] "
                         "[--quick] | self-test\n", why);
    std::exit(2);
}

Args parse(int argc, char** argv) {
    Args a;
    for (int i = 2; i < argc; ++i) {
        std::string k = argv[i];
        if (k.rfind("--", 0) != 0) {
            usage(("unexpected argument " + k).c_str());
        }
        k = k.substr(2);
        if (k == "quick") {
            a[k] = "1";
        } else if (i + 1 < argc) {
            a[k] = argv[++i];
        } else {
            usage(("missing value for --" + k).c_str());
        }
    }
    return a;
}

std::string get(const Args& a, const std::string& k, const std::string& def) {
    const auto it = a.find(k);
    return it == a.end() ? def : it->second;
}

int cmd_list() {
    for (const adv::Cell& c : adv::cells()) {
        std::printf("%s\t%s\t%u\t%s\t%s\n", c.id.c_str(), adv::family_name(c.table.family).c_str(), c.table.depth,
                    c.table.catch_all ? "catch-all" : "none", adv::query_name(c.query).c_str());
    }
    return 0;
}

rb::RouteId rb_id(const adv::Answer& a) {
    return a.status == 0 ? a.route : (a.status == 1 ? rb::kMethodNotAllowed : rb::kNoRoute);
}

int cmd_cell(const Args& a) {
    const std::string id = get(a, "cell", "");
    const adv::Cell* cell = nullptr;
    const std::vector<adv::Cell> all = adv::cells();
    for (const adv::Cell& c : all) {
        cell = c.id == id ? &c : cell;
    }
    if (cell == nullptr) {
        usage(("no cell named '" + id + "' (adversarial list)").c_str());
    }
    const adv::Table t = adv::make_table(cell->table);
    const adv::Request req = adv::request(t, cell->query);
    const adv::Answer want = adv::expected(t, cell->query);

    rb::MeasureOptions o;
    o.epochs = std::stoi(get(a, "epochs", "21"));
    if (a.count("quick") != 0) {
        o.build_reps = 1;
        o.epochs = 2;
        o.pass_budget_s = 0.02;
        o.latency_samples = 4096;
        o.latency_budget_s = 0.2;
    }
    // rbench's table and ring, holding only what the measurement reads: the cell's query in every
    // slot of the ring, with the answer it must get, and the cell's digests.
    rb::Table rt;
    rt.spec.m = static_cast<std::uint32_t>(t.patterns.size());
    rt.spec.seed = 0;
    rt.spec.methods = 2;
    rt.digest = t.digest;
    rb::Ring ring;
    ring.spec.size = static_cast<std::uint32_t>(std::stoul(get(a, "ring", "4096")));
    ring.spec.seed = 0;
    ring.spec.decoys = false;
    rb::Query q;
    q.method = static_cast<rb::Method>(req.method);
    q.path = req.path;
    q.expect = rb_id(want);
    for (std::size_t i = 0; i < want.values.size() && i < rb::kMaxParams; ++i) {
        q.caps.push_back(want.values[i]);
    }
    ring.queries.assign(ring.spec.size, q);
    ring.digest = rb::sha256_hex(t.digest + "\n" + std::to_string(req.method) + " " + req.path + "\n" +
                                 std::to_string(ring.spec.size));
    g_specs.clear();
    for (std::size_t i = 0; i < t.patterns.size(); ++i) {
        g_specs.push_back({t.methods[i], t.patterns[i], static_cast<std::uint32_t>(i)});
    }

    std::string measured;
    try {
        rb::ArmRunner<AdversarialArm> runner;
        measured = runner.measure(rt, ring, o);
    } catch (const std::exception& e) {
        rb::Json j;
        j.str("arm", AdversarialArm::info().name).str("status", "error").str("reason", e.what());
        measured = j.done();
    }

    // After the measurement: the pinned code's answer, the counting copy's answer and counts.
    const adv::Pinned pinned(t);
    adv::Counting counting(t);
    adv::Counts c;
    const adv::Answer pa = pinned.find(req);
    const adv::Answer ca = counting.find(req, c);
    const adv::Check k = adv::check(want, pa, ca, c);

    rb::Json j;
    j.str("tool", "adversarial").str("code_commit", ADV_CODE_COMMIT).str("regexmatcher_commit", RB_REGEXMATCHER_COMMIT);
    j.str("compiler", __VERSION__).str("build_type", RB_BUILD_TYPE).str("sanitizer", RB_SANITIZER);
    j.str("march", RB_ISA_MARCH).str("target_cpu", RB_ISA_TARGET_CPU);
    j.str("cell", cell->id).str("family", adv::family_name(cell->table.family)).num("depth", cell->table.depth);
    j.boolean("catch_all", cell->table.catch_all).str("query", adv::query_name(cell->query));
    j.str("method", std::string(rb::method_name(static_cast<rb::Method>(req.method)))).str("path", req.path);
    if (a.count("rep") != 0) {
        j.num("rep", std::stoi(get(a, "rep", "0")));
    }
    j.num("routes", t.patterns.size()).num("table_nodes", counting.nodes());
    j.num("trie_nodes_get", counting.trie_nodes(adv::kGet)).num("trie_nodes_put", counting.trie_nodes(adv::kPut));
    j.str("answer", adv::answer_text(pa)).str("expected", adv::answer_text(want));
    j.num("walks", c.walks).num("walked_nodes", c.walked_nodes).num("entries", c.entries);
    j.num("resumptions", c.resumptions).num("pushed", c.pushed).num("popped", c.popped);
    j.num("deepest_stack", c.deepest).num("max_entries_per_node", c.max_entries);
    j.num("max_resumptions_per_node", c.max_resumptions);
    j.boolean("expected_answer", k.expected_answer).boolean("same_answer", k.same_answer);
    j.boolean("bound_entries", k.bound_entries).boolean("bound_resumptions", k.bound_resumptions);
    j.boolean("checks_ok", k.ok());
    const std::string head = j.done();
    std::printf("%s,%s\n", head.substr(0, head.size() - 1).c_str(), measured.substr(1).c_str());
    std::fflush(stdout);  // a sanitizer report at exit must not lose the result line
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        usage("no command");
    }
    const std::string cmd = argv[1];
    if (cmd == "list") {
        return cmd_list();
    }
    if (cmd == "cell") {
        return cmd_cell(parse(argc, argv));
    }
    if (cmd == "self-test") {
        return adv::self_test(stdout) == 0 ? 0 : 1;
    }
    usage(("unknown command " + cmd).c_str());
}
