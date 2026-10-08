// The minimal server's v1 router arm (design/round2/minimal-server.md, section 2): RegexMatcher's
// engine at d16f30a8 behind the wrapper rbench's reference arm uses (bench/arms/
// regexmatcher_v1_wrap.hpp). Its translation unit sees only v1's include directory, as each arm
// of rbench does, so this interface names no RegexMatcher type.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

// The instruction set of this build (bench/cmake/isa.cmake), a compiled input of this target too.
#include "rb_isa.h"

namespace mserver::v1 {

// One method's lookup: the lowest matching route id (0xFFFFFFFF: none) and its captured values.
struct Lookup {
    std::uint32_t route = 0xFFFF'FFFFu;
    std::size_t count = 0;
    std::array<std::string_view, 16> values{};
};

class Router;

// The routes (method, pattern in rbench's syntax), route i being routes[i]. A pattern with no
// segment ("/") becomes the expression of the root path.
std::shared_ptr<Router> make(const std::vector<std::pair<unsigned, std::string>>& routes);

void match(Router& router, unsigned method, std::string_view path, Lookup& out);

}  // namespace mserver::v1
