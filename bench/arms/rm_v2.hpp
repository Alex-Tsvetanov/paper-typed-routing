// RegexMatcher v2's route matcher as the Lib of the adapter (arms/rm_arm.hpp), and the one
// out-of-line lookup both of its arms call.
#pragma once

#include <matcher/route.hpp>

#include <span>
#include <string_view>

namespace rb::rm {

// matcher::route::find compiled once, out of line (arms/regexmatcher_v2.cpp): the run-time and
// the compile-time arm call this same machine code and differ only in where the table lives.
matcher::route::Match find_v2(const matcher::route::TableView& view, unsigned method, std::string_view path);

struct V2 {
    using TableView = matcher::route::TableView;
    using Match = matcher::route::Match;
    using Built = matcher::route::RuntimeTable;  // the table in one page-aligned block
    using RouteSpec = matcher::route::RouteSpec;
    static constexpr auto kMethodNotAllowed = matcher::route::Status::MethodNotAllowed;
    static constexpr auto kBuildOk = matcher::route::BuildError::None;

    static Match find(const TableView& v, unsigned method, std::string_view path) { return find_v2(v, method, path); }
    static Built build(std::span<const RouteSpec> specs) { return matcher::route::make_runtime_table(specs); }
};

}  // namespace rb::rm
