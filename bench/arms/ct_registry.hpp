// The compile-time tables of bench/gen/, each registered under the digest of the table it was
// generated from (rbench gen-ct), so the regexmatcher-v2-ct arm can find the one that holds the
// routes it is given.
#pragma once

#include <matcher/route.hpp>

#include <cstddef>
#include <string_view>
#include <vector>

namespace rb::ct {

struct Entry {
    std::string_view digest;
    matcher::route::TableView view;
    std::size_t routes;
};

std::vector<Entry>& registry();

inline bool add(const Entry& e) {
    registry().push_back(e);
    return true;
}

}  // namespace rb::ct
