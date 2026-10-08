#include <algorithm>
#include <utility>

#include "core/arm.hpp"

// nanobench's implementation lives in this translation unit only.
#define ANKERL_NANOBENCH_IMPLEMENT
#include <nanobench.h>

namespace rb {
namespace {
std::vector<Registered>& table() {
    static std::vector<Registered> arms;
    return arms;
}
}  // namespace

bool register_arm(std::string name, Factory make) {
    auto& arms = table();
    arms.push_back({std::move(name), make});
    std::sort(arms.begin(), arms.end(), [](const auto& a, const auto& b) { return a.name < b.name; });
    return true;
}

const std::vector<Registered>& registered_arms() { return table(); }

}  // namespace rb
