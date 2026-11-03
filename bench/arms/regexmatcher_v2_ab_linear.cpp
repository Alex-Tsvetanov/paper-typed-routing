// regexmatcher-v2-ab-linear, an arm of design/review-runs/ablations.md: RegexMatcher v2's route headers at
// d1d73e99b, copied and renamed (arms/ablation/route_ab_linear.hpp, namespace matcher::route_ab_linear; generated
// and checked by tools/make_ablation.py), with one change: kLinearEdges above any node's edge count: every node linear.
// The table is built at run time into one page-aligned block (make_runtime_table) and looked up through
// the adapter of the v2 arms (arms/rm_arm.hpp) and its own out-of-line copy of the lookup,
// rb::rm::find_ab_linear, as regexmatcher-v2 is through rb::rm::find_v2 (arms/regexmatcher_v2.cpp).
// Exploratory: it decides nothing.
#include <span>
#include <string>
#include <string_view>

#include "arms/ablation/route_ab_linear.hpp"
#include "arms/rm_arm.hpp"

namespace rb::rm {

matcher::route_ab_linear::Match find_ab_linear(const matcher::route_ab_linear::TableView& view, unsigned method,
                                       std::string_view path);

struct AbLinear {
    using TableView = matcher::route_ab_linear::TableView;
    using Match = matcher::route_ab_linear::Match;
    using Built = matcher::route_ab_linear::RuntimeTable;  // the table in one page-aligned block
    using RouteSpec = matcher::route_ab_linear::RouteSpec;
    static constexpr auto kMethodNotAllowed = matcher::route_ab_linear::Status::MethodNotAllowed;
    static constexpr auto kBuildOk = matcher::route_ab_linear::BuildError::None;

    static Match find(const TableView& v, unsigned method, std::string_view path) { return find_ab_linear(v, method, path); }
    static Built build(std::span<const RouteSpec> specs) { return matcher::route_ab_linear::make_runtime_table(specs); }
};

}  // namespace rb::rm

[[gnu::noinline]] matcher::route_ab_linear::Match rb::rm::find_ab_linear(const matcher::route_ab_linear::TableView& view,
                                                              unsigned method, std::string_view path) {
    return matcher::route_ab_linear::find(view, method, path);
}

namespace {

struct Info {
    static rb::ArmInfo info() {
        return {"regexmatcher-v2-ab-linear", "RegexMatcher v2 d1d73e99b renamed (ablation: kLinearEdges above any node's edge count: every node linear)", "views into the path"};
    }
};

using AblationArm = rb::rm::Arm<rb::rm::AbLinear, rb::rm::RunTime<rb::rm::AbLinear>, Info>;

}  // namespace

RB_ARM(AblationArm)
