// The exploratory ablation arm: the round-1 header renamed but not re-engineered
// (arms/ablation/route_r1.hpp, namespace matcher::route_r1), built at run time and looked up
// through the same adapter as regexmatcher-v2 (arms/rm_arm.hpp), with its own out-of-line copy
// of the lookup, rb::rm::find_r1. Beside regexmatcher-v2 in every cell, it shows what round 2's
// engineering contributed; it decides nothing.
#include <span>
#include <string>
#include <string_view>

#include "arms/ablation/route_r1.hpp"
#include "arms/rm_arm.hpp"

namespace rb::rm {

matcher::route_r1::Match find_r1(const matcher::route_r1::TableView& view, unsigned method, std::string_view path);

struct R1 {
    using TableView = matcher::route_r1::TableView;
    using Match = matcher::route_r1::Match;
    using Built = matcher::route_r1::Built;
    using RouteSpec = matcher::route_r1::RouteSpec;
    static constexpr auto kMethodNotAllowed = matcher::route_r1::Status::MethodNotAllowed;
    static constexpr auto kBuildOk = matcher::route_r1::BuildError::None;

    static Match find(const TableView& v, unsigned method, std::string_view path) { return find_r1(v, method, path); }
    static Built build(std::span<const RouteSpec> specs) { return matcher::route_r1::build_table(specs); }
};

}  // namespace rb::rm

[[gnu::noinline]] matcher::route_r1::Match rb::rm::find_r1(const matcher::route_r1::TableView& view, unsigned method,
                                                          std::string_view path) {
    return matcher::route_r1::find(view, method, path);
}

namespace {

struct Info {
    static rb::ArmInfo info() {
        return {"regexmatcher-v2-r1", "RegexMatcher v2 at step E1 (00a2053), the round-1 header renamed (ablation)",
                "views into the path"};
    }
};

using RegexMatcherV2R1Arm = rb::rm::Arm<rb::rm::R1, rb::rm::RunTime<rb::rm::R1>, Info>;

}  // namespace

RB_ARM(RegexMatcherV2R1Arm)
