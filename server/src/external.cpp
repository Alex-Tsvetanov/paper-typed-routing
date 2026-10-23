// The registry of the server's external router arms: see external.hpp.
#include "external.hpp"

#include <string_view>
#include <utility>

namespace mserver {

namespace {

std::vector<ExternalArm>& registry() {
    static std::vector<ExternalArm> arms;
    return arms;
}

// The release round 3 pins for an arm whose round-2 adapter names an older one
// (server/cmake/pins-round3.cmake): "name=version|name=version". Empty: none.
std::string round3_version(std::string_view name) {
    std::string_view all = MSERVER_ROUND3_VERSIONS;
    while (!all.empty()) {
        const std::size_t bar = all.find('|');
        const std::string_view item = all.substr(0, bar);
        const std::size_t eq = item.find('=');
        if (eq != std::string_view::npos && item.substr(0, eq) == name) {
            return std::string(item.substr(eq + 1));
        }
        all = bar == std::string_view::npos ? std::string_view{} : all.substr(bar + 1);
    }
    return {};
}

}  // namespace

bool register_external(std::string name, std::string version, ExternalFactory make) {
    std::string pinned = round3_version(name);
    if (!pinned.empty()) {
        version = pinned + "; round 2's adapter: " + version;
    }
    registry().push_back({std::move(name), std::move(version), make});
    return true;
}

const std::vector<ExternalArm>& external_arms() { return registry(); }

}  // namespace mserver
