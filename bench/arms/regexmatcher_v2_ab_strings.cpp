// regexmatcher-v2-ab-strings, an ablation arm of quick-plan.md (the design choices of design/review-runs/ablations.md
// plus the two that quick-plan.md adds): RegexMatcher v2's route headers at d1d73e99b, copied and renamed
// (arms/ablation/route_ab_strings.hpp, namespace matcher::route_ab_strings; generated and checked by
// tools/make_ablation.py), with one change: a captured value owns a std::string copy of its bytes instead of a
// view into the path.
//
// The adapter differs from the other v2 arms' (arms/rm_arm.hpp) in one place, which the change forces: the
// harness reads a lookup's captured values as views after lookup() returns, and here they point into the
// strings the Match owns, so the adapter keeps the last Match as a member (moved into it from the out-of-line
// lookup) instead of letting it end with the call. That move is part of this arm's time; an owning design pays
// it wherever the answer outlives the call. Everything else is rm_arm.hpp's Arm: the table built at run time
// into one page-aligned block (RunTime), and the lookup through its own out-of-line copy,
// rb::rm::find_ab_strings, as regexmatcher-v2 is through rb::rm::find_v2 (arms/regexmatcher_v2.cpp).
// Exploratory: it decides nothing.
#include <span>
#include <string>
#include <string_view>

#include "arms/ablation/route_ab_strings.hpp"
#include "arms/rm_arm.hpp"

namespace rb::rm {

matcher::route_ab_strings::Match find_ab_strings(const matcher::route_ab_strings::TableView& view, unsigned method,
                                                 std::string_view path);

struct AbStrings {
    using TableView = matcher::route_ab_strings::TableView;
    using Match = matcher::route_ab_strings::Match;
    using Built = matcher::route_ab_strings::RuntimeTable;  // the table in one page-aligned block
    using RouteSpec = matcher::route_ab_strings::RouteSpec;
    static constexpr auto kMethodNotAllowed = matcher::route_ab_strings::Status::MethodNotAllowed;
    static constexpr auto kBuildOk = matcher::route_ab_strings::BuildError::None;

    static Match find(const TableView& v, unsigned method, std::string_view path) {
        return find_ab_strings(v, method, path);
    }
    static Built build(std::span<const RouteSpec> specs) { return matcher::route_ab_strings::make_runtime_table(specs); }
};

// rm_arm.hpp's Arm, with the last Match kept as a member so that the views handed to the harness stay valid.
template <class Lib, class Source, class Info>
class OwningArm final {
public:
    static constexpr bool native_405 = true;

    static ArmInfo info() { return Info::info(); }

    void add(const Route& r, RouteId id) { source_.add(r, id); }

    void finalize() { view_ = source_.template finalize<Lib>(); }

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        last_ = Lib::find(view_, static_cast<unsigned>(m), path);
        const typename Lib::Match& r = last_;
        c.n = r.count < kMaxParams ? r.count : static_cast<std::uint8_t>(kMaxParams);
        for (std::uint8_t i = 0; i < c.n; ++i) {
            c.v[i] = r.params[i];
        }
        if (r) {
            return r.route;
        }
        return r.status == Lib::kMethodNotAllowed ? kMethodNotAllowed : kNoRoute;
    }

    std::string table_layout() const { return layout_of(view_); }

private:
    typename Lib::TableView view_{};
    typename Lib::Match last_{};
    Source source_;
};

}  // namespace rb::rm

[[gnu::noinline]] matcher::route_ab_strings::Match rb::rm::find_ab_strings(
    const matcher::route_ab_strings::TableView& view, unsigned method, std::string_view path) {
    return matcher::route_ab_strings::find(view, method, path);
}

namespace {

struct Info {
    static rb::ArmInfo info() {
        return {"regexmatcher-v2-ab-strings",
                "RegexMatcher v2 d1d73e99b renamed (ablation: captured values owned as std::string copies)",
                "std::string copies, kept in the adapter's last Match"};
    }
};

using AblationArm = rb::rm::OwningArm<rb::rm::AbStrings, rb::rm::RunTime<rb::rm::AbStrings>, Info>;

}  // namespace

RB_ARM(AblationArm)
