// The C interface of v2 (capi/p2v2.h), the library the Go and Rust programs' v2 arms call, checked
// on round 3's request sets: for each cell directory given (t3/e2e_requests's layout: routes.txt,
// ring.txt and ring.expect, and all.txt and all.expect where written), p2v2_build builds the table
// from routes.txt, and p2v2_find must answer every path of each set with its line of the .expect
// file ("<route id>\t<value>..." as the servers' check mode writes it); a path no route matches must
// answer P2V2_NO_ROUTE. It also calls p2v2_build_info. D5's records run it under each sanitizer, so
// the library's code is covered where the Go and Rust programs cannot be instrumented.
//     test_p2v2 CELL_DIR...
#include "p2v2.h"

#include <cstdint>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

namespace {

std::vector<std::string> lines_of(const std::string& path, bool& ok) {
    std::ifstream in(path, std::ios::binary);
    std::vector<std::string> out;
    ok = static_cast<bool>(in);
    std::string line;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        if (!line.empty()) {
            out.push_back(line);
        }
    }
    return out;
}

std::string answer(const p2v2_table* table, const std::string& path) {
    std::uint32_t caps[2 * 64];
    std::uint32_t ncaps = 0;
    const std::uint32_t id = p2v2_find(table, 0, path.data(), path.size(), caps, 64, &ncaps);
    if (id == P2V2_NO_ROUTE) {
        return "miss";
    }
    std::string line = std::to_string(id);
    for (std::uint32_t i = 0; i < ncaps && i < 64; ++i) {
        line += '\t';
        line.append(path, caps[2 * i], caps[2 * i + 1]);
    }
    return line;
}

int check_set(const p2v2_table* table, const std::string& cell, const std::string& name, int& checked) {
    bool have_paths = false;
    bool have_expect = false;
    const auto paths = lines_of(cell + "/" + name + ".txt", have_paths);
    const auto expect = lines_of(cell + "/" + name + ".expect", have_expect);
    if (!have_paths && !have_expect && name == "all") {
        return 0;  // e2e_requests --no-all writes no all.txt
    }
    if (!have_paths || !have_expect || paths.size() != expect.size()) {
        std::fprintf(stderr, "%s: %s.txt and %s.expect missing or of different lengths\n", cell.c_str(), name.c_str(),
                     name.c_str());
        return 1;
    }
    int failures = 0;
    for (std::size_t i = 0; i < paths.size(); ++i) {
        const std::string got = answer(table, paths[i]);
        if (got != expect[i]) {
            if (++failures <= 5) {
                std::fprintf(stderr, "%s: %s line %zu: GET %s: want '%s', got '%s'\n", cell.c_str(), name.c_str(),
                             i + 1, paths[i].c_str(), expect[i].c_str(), got.c_str());
            }
        }
    }
    checked += static_cast<int>(paths.size());
    return failures;
}

int check_cell(const std::string& cell, int& checked) {
    bool ok = false;
    const auto routes = lines_of(cell + "/routes.txt", ok);
    if (!ok || routes.empty()) {
        std::fprintf(stderr, "%s: no routes.txt\n", cell.c_str());
        return 1;
    }
    std::vector<std::string> patterns;
    for (const std::string& r : routes) {
        if (r.rfind("GET /", 0) != 0) {
            std::fprintf(stderr, "%s: routes.txt: not \"GET <pattern>\": %s\n", cell.c_str(), r.c_str());
            return 1;
        }
        patterns.push_back(r.substr(4));
    }
    std::vector<const char*> ptrs;
    std::vector<std::size_t> lens;
    for (const std::string& p : patterns) {
        ptrs.push_back(p.data());
        lens.push_back(p.size());
    }
    char err[256] = {};
    p2v2_table* table = p2v2_build(ptrs.data(), lens.data(), ptrs.size(), err, sizeof err);
    if (table == nullptr) {
        std::fprintf(stderr, "%s: p2v2_build refused the routes: %s\n", cell.c_str(), err);
        return 1;
    }
    int failures = check_set(table, cell, "ring", checked) + check_set(table, cell, "all", checked);
    if (answer(table, "/p2-no-such-route/x/y/z/w") != "miss") {
        std::fprintf(stderr, "%s: a path no route matches did not answer P2V2_NO_ROUTE\n", cell.c_str());
        ++failures;
    }
    p2v2_free(table);
    return failures;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: test_p2v2 CELL_DIR...\n");
        return 2;
    }
    const char* info = p2v2_build_info();
    if (info == nullptr || *info == '\0') {
        std::fprintf(stderr, "p2v2_build_info returned nothing\n");
        return 1;
    }
    std::printf("p2v2: %s\n", info);
    int failures = 0;
    int checked = 0;
    for (int i = 1; i < argc; ++i) {
        failures += check_cell(argv[i], checked);
    }
    std::printf("test_p2v2: %d cells, %d paths, %d failures\n", argc - 1, checked, failures);
    return failures == 0 ? 0 : 1;
}
