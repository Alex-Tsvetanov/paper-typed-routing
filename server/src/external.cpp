// The registry of the server's external router arms: see external.hpp.
#include "external.hpp"

#include <utility>

namespace mserver {

namespace {

std::vector<ExternalArm>& registry() {
    static std::vector<ExternalArm> arms;
    return arms;
}

}  // namespace

bool register_external(std::string name, std::string version, ExternalFactory make) {
    registry().push_back({std::move(name), std::move(version), make});
    return true;
}

const std::vector<ExternalArm>& external_arms() { return registry(); }

}  // namespace mserver
