// regexmatcher-v2-ab-noexact, an arm of design/review-runs/ablations.md: RegexMatcher v2's route headers at
// d1d73e99b, copied and renamed (arms/ablation/route_ab_noexact.hpp, namespace matcher::route_ab_noexact; generated
// and checked by tools/make_ablation.py), with one change: no exact-match table: every route in its method's trie.
// The table is built at run time into one page-aligned block (make_runtime_table) and looked up through
// the adapter of the v2 arms (arms/rm_arm.hpp) and its own out-of-line copy of the lookup,
// rb::rm::find_ab_noexact, as regexmatcher-v2 is through rb::rm::find_v2 (arms/regexmatcher_v2.cpp).
// Exploratory: it decides nothing.
#include <span>
#include <string>
#include <string_view>

#include "arms/ablation/route_ab_noexact.hpp"
#include "arms/rm_arm.hpp"

namespace rb::rm {

matcher::route_ab_noexact::Match find_ab_noexact(const matcher::route_ab_noexact::TableView& view, unsigned method,
                                       std::string_view path);

struct AbNoexact {
    using TableView = matcher::route_ab_noexact::TableView;
    using Match = matcher::route_ab_noexact::Match;
    using Built = matcher::route_ab_noexact::RuntimeTable;  // the table in one page-aligned block
    using RouteSpec = matcher::route_ab_noexact::RouteSpec;
    static constexpr auto kMethodNotAllowed = matcher::route_ab_noexact::Status::MethodNotAllowed;
    static constexpr auto kBuildOk = matcher::route_ab_noexact::BuildError::None;

    static Match find(const TableView& v, unsigned method, std::string_view path) { return find_ab_noexact(v, method, path); }
    static Built build(std::span<const RouteSpec> specs) { return matcher::route_ab_noexact::make_runtime_table(specs); }
};

}  // namespace rb::rm

[[gnu::noinline]] matcher::route_ab_noexact::Match rb::rm::find_ab_noexact(const matcher::route_ab_noexact::TableView& view,
                                                              unsigned method, std::string_view path) {
    return matcher::route_ab_noexact::find(view, method, path);
}

namespace {

struct Info {
    static rb::ArmInfo info() {
        return {"regexmatcher-v2-ab-noexact", "RegexMatcher v2 d1d73e99b renamed (ablation: no exact-match table: every route in its method's trie)", "views into the path"};
    }
};

using AblationArm = rb::rm::Arm<rb::rm::AbNoexact, rb::rm::RunTime<rb::rm::AbNoexact>, Info>;

}  // namespace

RB_ARM(AblationArm)
