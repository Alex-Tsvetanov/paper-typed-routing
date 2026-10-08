// rbench: HTTP router lookups, one arm per router.
//
//   rbench list
//   rbench cell  --arm A --shape S --m M [--seed N] [--ring N] [--ring-seed N] [--miss PERMILLE]
//                [--zipf S] [--vocab long] [--no-decoy] [--ring-layout copy|queries] [--epochs E]
//                [--quick]
//   rbench agree [--arms A,B] [--sizes 10,100] [--shapes S,T] [--seeds 1,2] [--vocab long]
//                [--zipf S] [--no-decoy]
//   rbench probe --arm A
//   rbench gen-ct --out DIR [--seeds 1,111,...]
//
// cell prints one JSON object for one arm, table and ring. agree builds every listed arm on
// every listed table and checks each query of the ring (the cross-arm agreement test); it
// exits 1 if any arm disagrees with the expectation. probe prints one JSON object per probe
// query (core/probe.cpp). gen-ct writes the compile-time tables of the regexmatcher-v2-ct arm:
// one C++ file per shape at m = 10, 100 and 1,000 and per table seed (kTableSeeds, or --seeds),
// plus the github table, from the same generator as the grid's cells. (The test data of RegexMatcher's
// compile-time-table tests comes from tools/gen_route_tests.)
#include <cstdio>
#include <fstream>
#include <cstdlib>
#include <exception>
#include <map>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "core/alloc_count.hpp"
#include "core/arm.hpp"
#include "core/json.hpp"
#include "core/probe.hpp"
#include "core/table.hpp"

#ifndef RB_CODE_COMMIT
#define RB_CODE_COMMIT "unknown"
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

// The table seeds: 1, of engineering and iteration runs, and 111 to 126, held out for the
// round-2 publication run, one per process: run_grid.sh pairs table seed 110 + k with ring seed
// 210 + k (k = 1 to 16), so the sixteen pairs share no seed. The agreement test covers them all,
// and gen-ct compiles a table for each (bench/gen). Engineering and iteration runs use table
// seeds 1 to 5 and ring seeds 2 to 4, which round 1 used too; an iteration run that needs the
// compile-time tables of seeds 2 to 5 generates them (gen-ct --seeds) into a tree of its own.
// The publication run uses none of round 1's seeds.
constexpr const char* kTableSeeds = "1,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126";

[[noreturn]] void usage(const char* why) {
    std::fprintf(stderr, "rbench: %s\nusage: rbench list | cell --arm A --shape S --m M | agree | probe --arm A\n", why);
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
        if (k == "quick" || k == "no-decoy") {
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

std::vector<std::string> split(const std::string& s) {
    std::vector<std::string> out;
    std::size_t pos = 0;
    while (pos <= s.size()) {
        const std::size_t comma = s.find(',', pos);
        const std::size_t end = comma == std::string::npos ? s.size() : comma;
        if (end > pos) {
            out.push_back(s.substr(pos, end - pos));
        }
        pos = end + 1;
    }
    return out;
}

std::unique_ptr<rb::Runner> make(const std::string& name) {
    for (const auto& r : rb::registered_arms()) {
        if (r.name == name) {
            return r.make();
        }
    }
    usage(("no arm named " + name + " in this build").c_str());
}

// Build facts added to every result line.
std::string with_build(const std::string& obj) {
    rb::Json j;
    j.str("code_commit", RB_CODE_COMMIT).str("regexmatcher_commit", RB_REGEXMATCHER_COMMIT);
    j.str("compiler", __VERSION__).str("build_type", RB_BUILD_TYPE).str("sanitizer", RB_SANITIZER);
    j.str("march", RB_ISA_MARCH).str("target_cpu", RB_ISA_TARGET_CPU).str("rust_target_cpu", RB_ISA_RUST_CPU);
    j.str("goamd64", RB_ISA_GOAMD64);
    const std::string head = j.done();
    return head.substr(0, head.size() - 1) + "," + obj.substr(1);
}

std::uint64_t num(const Args& a, const std::string& k, std::uint64_t def) {
    return std::stoull(get(a, k, std::to_string(def)));
}

int cmd_list() {
    for (const auto& r : rb::registered_arms()) {
        const rb::ArmInfo info = r.make()->describe();
        std::printf("%s\t%s\t%s\n", info.name.c_str(), info.version.c_str(), info.captures.c_str());
    }
    std::printf("# allocation counting: %s\n", rb::alloc::mechanism());
    return 0;
}

int cmd_cell(const Args& a) {
    rb::TableSpec ts;
    if (!rb::parse_shape(get(a, "shape", ""), ts.shape)) {
        usage("--shape must be static, param-last, param-first, rest, wild, mixed-disjoint, mixed-overlap or github");
    }
    ts.m = static_cast<std::uint32_t>(num(a, "m", 0));
    ts.seed = num(a, "seed", 1);
    ts.long_words = get(a, "vocab", "default") == "long";
    rb::RingSpec rs;
    rs.size = static_cast<std::uint32_t>(num(a, "ring", 4096));
    rs.seed = num(a, "ring-seed", 2);
    rs.miss_permille = static_cast<std::uint32_t>(num(a, "miss", 0));
    rs.zipf = std::stod(get(a, "zipf", "0"));
    rs.decoys = a.count("no-decoy") == 0;
    rb::MeasureOptions o;
    o.epochs = static_cast<int>(num(a, "epochs", 21));
    o.ring_from_queries = get(a, "ring-layout", "copy") == "queries";
    if (a.count("quick") != 0) {
        o.build_reps = 1;
        o.epochs = 2;
        o.pass_budget_s = 0.02;
        o.latency_samples = 4096;
        o.latency_budget_s = 0.2;
    }
    auto arm = make(get(a, "arm", ""));
    const rb::Table t = rb::generate_table(ts);
    const rb::Ring r = rb::generate_ring(t, rs);
    std::string line;
    try {
        line = arm->measure(t, r, o);
    } catch (const std::exception& e) {
        rb::Json j;
        j.str("arm", arm->describe().name).str("shape", rb::shape_name(ts.shape)).num("m", ts.m);
        j.str("status", "error").str("reason", e.what());
        line = j.done();
    }
    std::printf("%s\n", with_build(line).c_str());
    std::fflush(stdout);  // a sanitizer report at exit must not lose the result line
    return 0;
}

int cmd_agree(const Args& a) {
    std::vector<std::string> arms = split(get(a, "arms", ""));
    if (arms.empty()) {
        for (const auto& r : rb::registered_arms()) {
            arms.push_back(r.name);
        }
    }
    std::vector<rb::Shape> shapes;
    for (const auto& s : split(get(a, "shapes", "static,param-last,param-first,rest,wild,mixed-disjoint,mixed-overlap,github"))) {
        rb::Shape sh{};
        if (!rb::parse_shape(s, sh)) {
            usage(("unknown shape " + s).c_str());
        }
        shapes.push_back(sh);
    }
    int bad = 0;
    bool github_done = false;  // the github table has one size and no seed
    for (const auto& seed : split(get(a, "seeds", kTableSeeds)))
    for (const auto& size : split(get(a, "sizes", "10,100,1000"))) {
        for (rb::Shape sh : shapes) {
            if (sh == rb::Shape::Github && std::exchange(github_done, true)) {
                continue;
            }
            const rb::Table t = rb::generate_table({sh, static_cast<std::uint32_t>(std::stoul(size)),
                                                     std::stoull(seed), 1, get(a, "vocab", "default") == "long"});
            const rb::Ring r = rb::generate_ring(t, {1024, 2, 0, std::stod(get(a, "zipf", "0")), a.count("no-decoy") == 0});
            const rb::RingWalk w = rb::ring_walk(t, r);
            for (const auto& name : arms) {
                auto arm = make(name);
                if (arm->describe().null) {
                    continue;  // no router, nothing to agree on
                }
                rb::Json j;
                j.str("arm", name).str("shape", rb::shape_name(sh)).num("m", t.spec.m).num("table_seed", t.spec.seed);
                j.num("queries", r.queries.size());
                j.num("ring_exact", w.exact).num("ring_backtracking", w.backtracking).num("ring_pops", w.pops);
                try {
                    arm->build(t.routes);
                    // The wrong answers by kind, which bench/semantics.json declares per arm and
                    // shape: another route or none (and of those, "no route"), or the right route
                    // with other captured values.
                    std::uint64_t wrong = 0;
                    std::uint64_t ids = 0;
                    std::uint64_t ids_404 = 0;
                    std::uint64_t values = 0;
                    std::string first;
                    std::vector<std::string> caps;
                    for (const auto& q : r.queries) {
                        const rb::RouteId id = arm->lookup(q.method, q.path, caps);
                        bool ok = id == q.expect;
                        if (!ok) {
                            ++ids;
                            ids_404 += id == rb::kNoRoute ? 1u : 0u;
                        } else {
                            ok = caps.size() == q.caps.size();
                            for (std::size_t i = 0; ok && i < caps.size(); ++i) {
                                const bool rest = sh == rb::Shape::Wild && i + 1 == caps.size();
                                std::string_view g = caps[i];
                                if (rest && g.size() == q.caps[i].size() + 1 && g.front() == '/') {
                                    g.remove_prefix(1);
                                }
                                ok = g == q.caps[i];
                            }
                            values += ok ? 0u : 1u;
                        }
                        if (!ok && wrong++ == 0) {
                            first = q.path + " -> " + std::to_string(id);
                        }
                    }
                    j.num("wrong", wrong).num("id_mismatches", ids).num("id_mismatches_404", ids_404);
                    j.num("capture_mismatches", values);
                    j.str("first_wrong", first).str("status", wrong == 0 ? "agrees" : "disagrees");
                    bad += wrong != 0;
                } catch (const rb::Refused& e) {
                    j.str("status", "refused").str("reason", e.what());
                } catch (const std::exception& e) {
                    j.str("status", "error").str("reason", e.what());
                    ++bad;
                }
                std::printf("%s\n", with_build(j.done()).c_str());
                std::fflush(stdout);
            }
        }
    }
    return bad == 0 ? 0 : 1;
}

std::string cxx_string(std::string_view s) {
    std::string out = "\"";
    for (const char ch : s) {
        if (ch == '"' || ch == '\\') {
            out += '\\';
        }
        out += ch;
    }
    return out + '"';
}

int cmd_gen_ct(const Args& a) {
    const std::string dir = get(a, "out", "");
    if (dir.empty()) {
        usage("gen-ct needs --out DIR");
    }
    struct Want {
        rb::Shape shape;
        std::uint32_t m;
        std::uint64_t seed;
    };
    std::vector<Want> tables;
    for (const auto& seed : split(get(a, "seeds", kTableSeeds))) {
        for (rb::Shape sh : rb::kShapes) {
            for (std::uint32_t m : {10u, 100u, 1000u}) {
                tables.push_back({sh, m, std::stoull(seed)});
            }
        }
    }
    tables.push_back({rb::Shape::Github, rb::kGithubRoutes, 1});  // one table, whatever the seed
    for (const auto& [sh, m, seed] : tables) {
        {
            const rb::Table t = rb::generate_table({sh, m, seed, 1});
            std::string name(rb::shape_name(sh));
            for (char& c : name) {
                c = c == '-' ? '_' : c;
            }
            name += "_" + std::to_string(m);
            if (sh != rb::Shape::Github) {
                name += "_s" + std::to_string(seed);
            }
            const std::string file = dir + "/ct_" + name + ".cpp";
            std::ofstream f(file, std::ios::binary);
            f << "// Generated by `rbench gen-ct`: the " << rb::shape_name(sh) << " table of " << m
              << " routes, table seed " << seed << ",\n// as a compile-time table for the regexmatcher-v2-ct arm. Do not edit.\n"
              << "#include \"arms/ct_registry.hpp\"\n\nnamespace {\n\nusing matcher::route::RouteSpec;\n\n"
              << "constexpr RouteSpec kRoutes[] = {\n";
            for (std::size_t i = 0; i < t.routes.size(); ++i) {
                f << "    {" << static_cast<unsigned>(t.routes[i].method) << "u, " << cxx_string(rb::render(t.routes[i]))
                  << ", " << i << "u},\n";
            }
            // Page-aligned, as RegexMatcher v2's RuntimeTable is, so that every element of the two
            // arms' tables lies at the same offset into a page (design/round2/engineering.md, C2).
            f << "};\n\nalignas(matcher::route::kPageAlign) constexpr auto kTable = "
                 "matcher::route::make_static_table<kRoutes>();\n\n"
              << "[[maybe_unused]] const bool kRegistered =\n    rb::ct::add({" << cxx_string(t.digest)
              << ", kTable.view(), " << t.routes.size() << "});\n\n}  // namespace\n";
            if (!f) {
                std::fprintf(stderr, "rbench: cannot write %s\n", file.c_str());
                return 1;
            }
            std::printf("%s %s\n", file.c_str(), t.digest.c_str());
        }
    }
    return 0;
}

int cmd_probe(const Args& a) {
    auto arm = make(get(a, "arm", ""));
    if (arm->describe().null) {
        rb::Json j;
        j.str("arm", arm->describe().name).str("status", "not applicable").str("reason", "the null arm has no router");
        std::printf("%s\n", with_build(j.done()).c_str());
        return 0;
    }
    for (const auto& line : rb::run_probes(*arm)) {
        std::printf("%s\n", with_build(line).c_str());
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        usage("no command");
    }
    const std::string cmd = argv[1];
    const Args a = parse(argc, argv);
    try {
        if (cmd == "list") return cmd_list();
        if (cmd == "cell") return cmd_cell(a);
        if (cmd == "agree") return cmd_agree(a);
        if (cmd == "probe") return cmd_probe(a);
        if (cmd == "gen-ct") return cmd_gen_ct(a);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "rbench: %s\n", e.what());
        return 1;
    }
    usage("unknown command");
}
