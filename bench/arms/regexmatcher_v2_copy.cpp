// regexmatcher-v2-copy, an arm of design/review-runs/ablations.md: RegexMatcher v2's route headers at
// d1d73e99b, copied and renamed (arms/ablation/route_copy.hpp, namespace matcher::route_copy; generated
// and checked by tools/make_ablation.py), with no other change: the control of every ablation variant.
// The table is built at run time into one page-aligned block (make_runtime_table) and looked up through
// the adapter of the v2 arms (arms/rm_arm.hpp) and its own out-of-line copy of the lookup,
// rb::rm::find_copy, as regexmatcher-v2 is through rb::rm::find_v2 (arms/regexmatcher_v2.cpp).
// Exploratory: it decides nothing.
#include <span>
#include <string>
#include <string_view>

#include "arms/ablation/route_copy.hpp"
#include "arms/rm_arm.hpp"

namespace rb::rm {

matcher::route_copy::Match find_copy(const matcher::route_copy::TableView& view, unsigned method,
                                       std::string_view path);

struct Copy {
    using TableView = matcher::route_copy::TableView;
    using Match = matcher::route_copy::Match;
    using Built = matcher::route_copy::RuntimeTable;  // the table in one page-aligned block
    using RouteSpec = matcher::route_copy::RouteSpec;
    static constexpr auto kMethodNotAllowed = matcher::route_copy::Status::MethodNotAllowed;
    static constexpr auto kBuildOk = matcher::route_copy::BuildError::None;

    static Match find(const TableView& v, unsigned method, std::string_view path) { return find_copy(v, method, path); }
    static Built build(std::span<const RouteSpec> specs) { return matcher::route_copy::make_runtime_table(specs); }
};

}  // namespace rb::rm

[[gnu::noinline]] matcher::route_copy::Match rb::rm::find_copy(const matcher::route_copy::TableView& view,
                                                              unsigned method, std::string_view path) {
    return matcher::route_copy::find(view, method, path);
}

namespace {

struct Info {
    static rb::ArmInfo info() {
        return {"regexmatcher-v2-copy", "RegexMatcher v2 d1d73e99b, the renamed copy (the ablations' control)", "views into the path"};
    }
};

using AblationArm = rb::rm::Arm<rb::rm::Copy, rb::rm::RunTime<rb::rm::Copy>, Info>;

}  // namespace

RB_ARM(AblationArm)
