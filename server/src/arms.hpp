// The minimal server's router arms (design/round2/minimal-server.md, section 2), behind the one
// function pointer of route.hpp.
#pragma once

#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "route.hpp"

namespace mserver {

struct RouteLine {
    unsigned method;
    std::string pattern;  // rbench's syntax: {name} a parameter, {*name} a catch-all
};

// The routes file h6_targets writes: one "GET <pattern>" per line. Throws std::runtime_error on
// a line of another form, or a method other than GET.
std::vector<RouteLine> read_routes(const std::string& path);

// A router arm and the data it answers from. The arm routes the file's routes, route i being the
// file's line i, and GET / (the readiness probe of lab/t1) as the route after them, unless the
// file has it.
struct Arm {
    Router router;
    std::shared_ptr<const void> data;
};

// "v2": RegexMatcher v2's run-time table, looked up with find_into. "v1": RegexMatcher's engine
// at d16f30a8 behind rbench's wrapper (arm_v1.hpp). "null": route 0 for every request, without
// reading the path. Throws std::runtime_error for another name, or when the routes do not build
// a table.
Arm make_arm(std::string_view name, const std::vector<RouteLine>& routes);

}  // namespace mserver
