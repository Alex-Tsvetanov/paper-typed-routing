// The routes and targets of one H6 cell (hypotheses.md, H6): the T0 table of a shape and size
// (rbench's generator, bench/core/table.cpp, unchanged), and one request target per route.
//
//     h6_targets --shape S --m M [--table-seed 101] [--ring-seed 201] --routes FILE --targets FILE
//
// FILE of --routes: one route per line, "GET <pattern>", in the table's registration order,
// in rbench's canonical syntax ("/a/{p0}/{*p1}"); h6_server reads it. Only GET tables are
// written (the T0 tables have one method), and anything else is refused.
//
// FILE of --targets: one path per route, for t1gen --paths. The paths are those of a T0 ring
// of the table with the ring seed (generate_ring, so every parameter is filled as the ring
// fills it, decoys included); for each route, the first query of the ring that the reference
// matcher answers with that route. The ring is 32 queries per route, and doubled until every
// route has a query. The lines are then shuffled with the ring seed (rng.hpp's shuffle, the
// same order on every standard library). Prints the table digest, the ring size used and a
// sha256 of each file's text.
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include "core/rng.hpp"
#include "core/table.hpp"

namespace {

std::string sha256_hex_of(const std::string& text) { return rb::sha256_hex(text); }

int fail(const std::string& why) {
    std::cerr << "h6_targets: " << why << "\n";
    return 2;
}

}  // namespace

int main(int argc, char** argv) {
    std::string shape_text, routes_path, targets_path;
    std::uint32_t m = 0;
    std::uint64_t table_seed = 101, ring_seed = 201;
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
            } else if (a == "--routes") {
                routes_path = value();
            } else if (a == "--targets") {
                targets_path = value();
            } else {
                throw std::invalid_argument("unknown argument " + std::string(a));
            }
        }
    } catch (const std::exception& e) {
        return fail(e.what());
    }
    rb::Shape shape{};
    if (!rb::parse_shape(shape_text, shape) || m == 0 || routes_path.empty() || targets_path.empty()) {
        return fail("usage: h6_targets --shape S --m M [--table-seed N] [--ring-seed N] --routes FILE --targets FILE");
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
        std::vector<std::string> targets;
        std::uint32_t size = 32 * static_cast<std::uint32_t>(table.routes.size());
        while (true) {
            const rb::Ring ring = rb::generate_ring(table, {size, ring_seed});
            std::vector<std::string> first(table.routes.size());
            std::size_t found = 0;
            for (const rb::Query& q : ring.queries) {
                if (q.expect < first.size() && first[q.expect].empty()) {
                    first[q.expect] = q.path;
                    ++found;
                }
            }
            if (found == first.size()) {
                targets = std::move(first);
                break;
            }
            if (size > (1u << 30) / 2) {
                return fail("some route is never the answer of a ring query");
            }
            size *= 2;
        }
        rb::SplitMix64 rng(ring_seed);
        rb::shuffle(rng, targets);
        std::string targets_text;
        for (const std::string& t : targets) {
            targets_text += t + "\n";
        }
        std::ofstream(routes_path, std::ios::binary) << routes_text;
        std::ofstream(targets_path, std::ios::binary) << targets_text;
        std::cout << "shape " << rb::shape_name(shape) << " m " << m << " table_seed " << table_seed
                  << " ring_seed " << ring_seed << " table_digest " << table.digest << " ring_size " << size
                  << " routes_sha256 " << sha256_hex_of(routes_text) << " targets_sha256 "
                  << sha256_hex_of(targets_text) << "\n";
    } catch (const std::exception& e) {
        return fail(e.what());
    }
    return 0;
}
