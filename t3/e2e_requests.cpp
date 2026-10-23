// The request set of one round-3 cell (design/round3/end-to-end.md, section 4): the T0 table of a
// shape, size and table seed (rbench's generator, bench/core/table.cpp, unchanged), its T0 ring at
// the ring seed, and one target per route.
//
//     e2e_requests --shape S --m M --table-seed N --ring-seed N --out DIR [--no-all]
//
// Writes into DIR (which must exist):
//   routes.txt   one route per line, "GET <pattern>", in registration order, in rbench's canonical
//                syntax ("/a/{p0}/{*p1}"); route i is line i. Only GET tables are written.
//   ring.txt     the T0 ring (generate_ring at the ring seed, its default size of 4,096), one path
//                per line in ring order: the measured request set.
//   ring.expect  per line of ring.txt, the expected answer as the servers' check mode writes it:
//                the route id in decimal, then a tab and each captured value.
//   all.txt      one path per route, as t1/h6_targets chooses it: the first query of a ring of 32
//                queries per route (doubled until every route has one) that the reference matcher
//                answers with that route; shuffled with the ring seed.
//   all.expect   per line of all.txt, as ring.expect.
//   With --no-all, all.txt and all.expect are not written (their digests print as "-"): at
//   m = 100,000 they take minutes per cell, and the functional check of every route needs them
//   for one seed pair only.
// Prints one line: the cell, the table and ring digests, and the sha256 of each file's text.
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include "core/rng.hpp"
#include "core/table.hpp"

namespace {

int fail(const std::string& why) {
    std::cerr << "e2e_requests: " << why << "\n";
    return 2;
}

std::string expect_line(const rb::Query& q) {
    std::string line = std::to_string(q.expect);
    for (const std::string& v : q.caps) {
        line += '\t';
        line += v;
    }
    return line;
}

// The paths and expected answers of queries, one per line each; returns the two texts.
std::pair<std::string, std::string> write_queries(const std::filesystem::path& dir, const std::string& stem,
                                                  const std::vector<rb::Query>& qs) {
    std::string paths_text, expect_text;
    for (const rb::Query& q : qs) {
        paths_text += q.path + "\n";
        expect_text += expect_line(q) + "\n";
    }
    std::ofstream(dir / (stem + ".txt"), std::ios::binary) << paths_text;
    std::ofstream(dir / (stem + ".expect"), std::ios::binary) << expect_text;
    return {paths_text, expect_text};
}

// One query per route: the first query of a ring of the table that the reference matcher answers
// with that route (t1/h6_targets.cpp's rule), shuffled with the ring seed.
std::vector<rb::Query> one_per_route(const rb::Table& table, std::uint64_t ring_seed) {
    std::uint32_t size = 32 * static_cast<std::uint32_t>(table.routes.size());
    while (true) {
        const rb::Ring ring = rb::generate_ring(table, {size, ring_seed});
        std::vector<rb::Query> first(table.routes.size());
        std::vector<bool> have(table.routes.size(), false);
        std::size_t found = 0;
        for (const rb::Query& q : ring.queries) {
            if (q.expect < first.size() && !have[q.expect]) {
                first[q.expect] = q;
                have[q.expect] = true;
                ++found;
            }
        }
        if (found == first.size()) {
            rb::SplitMix64 rng(ring_seed);
            rb::shuffle(rng, first);
            return first;
        }
        if (size > (1u << 30) / 2) {
            throw std::runtime_error("some route is never the answer of a ring query");
        }
        size *= 2;
    }
}

}  // namespace

int main(int argc, char** argv) {
    std::string shape_text, out_dir;
    std::uint32_t m = 0;
    std::uint64_t table_seed = 0, ring_seed = 0;
    bool with_all = true;
    try {
        for (int i = 1; i < argc; ++i) {
            const std::string_view a = argv[i];
            const auto value = [&]() -> std::string {
                if (i + 1 >= argc) {
                    throw std::invalid_argument(std::string(a) + " needs a value");
                }
                return argv[++i];
            };
            if (a == "--shape") {
                shape_text = value();
            } else if (a == "--m") {
                m = static_cast<std::uint32_t>(std::stoul(value()));
            } else if (a == "--table-seed") {
                table_seed = std::stoull(value());
            } else if (a == "--ring-seed") {
                ring_seed = std::stoull(value());
            } else if (a == "--out") {
                out_dir = value();
            } else if (a == "--no-all") {
                with_all = false;
            } else {
                throw std::invalid_argument("unknown argument " + std::string(a));
            }
        }
    } catch (const std::exception& e) {
        return fail(e.what());
    }
    rb::Shape shape{};
    if (!rb::parse_shape(shape_text, shape) || m == 0 || table_seed == 0 || ring_seed == 0 || out_dir.empty()) {
        return fail("usage: e2e_requests --shape S --m M --table-seed N --ring-seed N --out DIR [--no-all]");
    }
    const std::filesystem::path dir(out_dir);
    if (!std::filesystem::is_directory(dir)) {
        return fail("--out " + out_dir + " is not a directory");
    }
    try {
        const rb::Table table = rb::generate_table({shape, m, table_seed, 1});
        std::string routes_text;
        for (const rb::Route& r : table.routes) {
            if (r.method != rb::Method::Get) {
                return fail("the table has a route that is not GET: " + rb::render(r));
            }
            routes_text += "GET " + rb::render(r) + "\n";
        }
        std::ofstream(dir / "routes.txt", std::ios::binary) << routes_text;

        const rb::Ring ring = rb::generate_ring(table, {4096, ring_seed});
        const auto [ring_text, ring_expect] = write_queries(dir, "ring", ring.queries);
        std::string all_sha = "-", all_expect_sha = "-";
        if (with_all) {
            const auto [all_text, all_expect] = write_queries(dir, "all", one_per_route(table, ring_seed));
            all_sha = rb::sha256_hex(all_text);
            all_expect_sha = rb::sha256_hex(all_expect);
        }

        std::cout << "shape " << rb::shape_name(shape) << " m " << m << " table_seed " << table_seed << " ring_seed "
                  << ring_seed << " table_digest " << table.digest << " ring_digest " << ring.digest
                  << " routes_sha256 " << rb::sha256_hex(routes_text) << " ring_sha256 " << rb::sha256_hex(ring_text)
                  << " ring_expect_sha256 " << rb::sha256_hex(ring_expect) << " all_sha256 " << all_sha
                  << " all_expect_sha256 " << all_expect_sha << "\n";
    } catch (const std::exception& e) {
        return fail(e.what());
    }
    return 0;
}
