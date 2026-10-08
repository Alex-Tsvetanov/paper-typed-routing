// The router arms' agreement on H6's tables (design/round2/minimal-server.md, section 5): for each
// routes file and targets file that t1/h6_targets writes, every target is answered with the same
// route and the same captured values by the v1 and v2 arms, the route being found, and with
// route 0 by the null arm. Run by server/tests/h6_agreement.cmake over the nine H6 cells.
//     test_agreement ROUTES TARGETS [ROUTES TARGETS ...]
#include <cstdio>
#include <fstream>
#include <string>
#include <string_view>
#include <vector>

#include "arms.hpp"

namespace {

using namespace mserver;

std::vector<std::string> lines(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    std::vector<std::string> out;
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

std::vector<std::string> values(const RouteResult& r) {
    std::vector<std::string> v;
    for (std::uint8_t i = 0; i < r.count; ++i) {
        v.emplace_back(r.params[i].view());
    }
    return v;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3 || argc % 2 != 1) {
        std::fprintf(stderr, "usage: test_agreement ROUTES TARGETS [ROUTES TARGETS ...]\n");
        return 2;
    }
    int bad_files = 0;
    for (int i = 1; i + 1 < argc; i += 2) {
        const std::vector<RouteLine> routes = read_routes(argv[i]);
        const std::vector<std::string> targets = lines(argv[i + 1]);
        const Arm v2 = make_arm("v2", routes);
        const Arm v1 = make_arm("v1", routes);
        const Arm null = make_arm("null", routes);
        RouteResult a, b, n;
        std::size_t differ = 0, missed = 0, null_bad = 0;
        for (const std::string& t : targets) {
            const std::string_view path = std::string_view(t).substr(0, t.find('?'));
            v2.router(kGet, path, a);
            v1.router(kGet, path, b);
            null.router(kGet, path, n);
            missed += a.status != RouteStatus::Found;
            differ += a.status != b.status || a.route != b.route || values(a) != values(b);
            null_bad += n.status != RouteStatus::Found || n.route != 0;
        }
        const bool ok = !targets.empty() && differ == 0 && missed == 0 && null_bad == 0;
        bad_files += !ok;
        std::printf("%s: %zu routes, %zu targets; v2 not found %zu; v1 and v2 differ %zu; null not route 0 %zu: %s\n",
                    argv[i], routes.size(), targets.size(), missed, differ, null_bad, ok ? "agree" : "DISAGREE");
    }
    return bad_files == 0 ? 0 : 1;
}
