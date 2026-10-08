// Correctness probes: small hand-written tables that ask what an arm does where routers
// differ. They are not timed and not part of the agreement test.
#pragma once

#include <string>
#include <vector>

#include "core/arm.hpp"

namespace rb {

// One JSON line per query: the case, the rule it tests, the expected and the actual result.
std::vector<std::string> run_probes(Runner& arm);

}  // namespace rb
