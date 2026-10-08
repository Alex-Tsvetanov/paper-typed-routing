// A check of answers only, with no timing, for processes of an rbench run whose agreement
// pass stopped at its time budget (a cell's pass stops after 120 s, verified_all false).
// It is linked from the run's own rbench build: every object of rbench but main.cpp's, with
// this file in its place (tools/build_verify.sh), so the arms and bench/core are the same
// object code the run measured.
//
//     verify_answers --arm A --shape S --m M --seed T --ring-seed R [--ring 4096] [--miss PERMILLE]
//                    [--zipf S] [--vocab long] [--no-decoy 1]
//
// The table and the ring are those of `rbench cell` with the same arguments (by default no
// misses, no Zipf, decoys on, the default vocabulary). The arm is built once and every query is looked
// up and compared as the cell's agreement pass compares it: the route id, then every
// captured value, where a catch-all's value with a leading '/' is the same value. Prints one
// JSON line: the arm, table, seeds and digests, the queries checked and the mismatches.
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "core/arm.hpp"
#include "core/json.hpp"
#include "core/runner.hpp"
#include "core/table.hpp"

namespace {

std::map<std::string, std::string> parse(int argc, char** argv) {
    std::map<std::string, std::string> a;
    for (int i = 1; i + 1 < argc; i += 2) {
        std::string k = argv[i];
        if (k.rfind("--", 0) != 0) {
            std::fprintf(stderr, "verify_answers: bad argument %s\n", argv[i]);
            std::exit(2);
        }
        a[k.substr(2)] = argv[i + 1];
    }
    return a;
}

}  // namespace

int main(int argc, char** argv) {
    auto a = parse(argc, argv);
    rb::TableSpec ts;
    if (!rb::parse_shape(a["shape"], ts.shape) || a["m"].empty() || a["arm"].empty()) {
        std::fprintf(stderr, "usage: verify_answers --arm A --shape S --m M --seed T --ring-seed R [--ring N]\n");
        return 2;
    }
    ts.m = static_cast<std::uint32_t>(std::stoul(a["m"]));
    ts.seed = a.count("seed") ? std::stoull(a["seed"]) : 1;
    ts.long_words = a.count("vocab") != 0 && a["vocab"] == "long";
    rb::RingSpec rs;
    rs.size = a.count("ring") ? static_cast<std::uint32_t>(std::stoul(a["ring"])) : 4096;
    rs.seed = a.count("ring-seed") ? std::stoull(a["ring-seed"]) : 2;
    rs.miss_permille = a.count("miss") ? static_cast<std::uint32_t>(std::stoul(a["miss"])) : 0;
    rs.zipf = a.count("zipf") ? std::stod(a["zipf"]) : 0.0;
    rs.decoys = a.count("no-decoy") == 0;
    std::unique_ptr<rb::Runner> arm;
    for (const auto& r : rb::registered_arms()) {
        if (r.name == a["arm"]) {
            arm = r.make();
        }
    }
    if (!arm) {
        std::fprintf(stderr, "verify_answers: no arm named %s in this build\n", a["arm"].c_str());
        return 2;
    }
    const rb::Table t = rb::generate_table(ts);
    const rb::Ring r = rb::generate_ring(t, rs);
    rb::Json j;
    j.str("arm", a["arm"]).str("shape", rb::shape_name(ts.shape)).num("m", ts.m).num("table_seed", ts.seed);
    j.num("ring_seed", rs.seed).str("table_digest", t.digest).str("ring_digest", r.digest);
    std::uint64_t checked = 0, id_bad = 0, cap_bad = 0;
    std::vector<std::string> examples;
    try {
        arm->build(t.routes);
        std::vector<std::string> caps;
        for (const rb::Query& q : r.queries) {
            ++checked;
            const rb::RouteId id = arm->lookup(q.method, q.path, caps);
            bool ok = id == q.expect;
            if (!ok) {
                ++id_bad;
            } else {
                bool caps_ok = caps.size() == q.caps.size();
                for (std::size_t i = 0; caps_ok && i < caps.size(); ++i) {
                    caps_ok = rb::detail::same_value(caps[i], q.caps[i], rb::detail::rest_capture(t, id, i));
                }
                if (!caps_ok) {
                    ++cap_bad;
                    ok = false;
                }
            }
            if (!ok && examples.size() < 50) {
                examples.push_back(q.path + " -> " + std::to_string(id) + " (want " + std::to_string(q.expect) + ")");
            }
        }
        j.num("queries", r.queries.size()).num("checked", checked).num("id_mismatches", id_bad);
        j.num("capture_mismatches", cap_bad).boolean("agrees_all", checked == r.queries.size() && id_bad == 0 &&
                                                                        cap_bad == 0);
        std::string ex;
        for (const auto& e : examples) {
            ex += (ex.empty() ? "" : " | ") + e;
        }
        j.str("examples", ex).str("status", "checked");
    } catch (const std::exception& e) {
        j.str("status", "error").str("reason", e.what());
    }
    std::printf("%s\n", j.done().c_str());
    return 0;
}
