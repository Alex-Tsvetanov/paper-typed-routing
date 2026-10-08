// RegexMatcher v2's table built at run time (the arm of H1 to H4): make_runtime_table over the
// routes (build_table's table, copied into one page-aligned block laid out as the compile-time
// table), then matcher::route::find through rb::rm::find_v2, the one out-of-line copy of the
// lookup that the compile-time table's arm (arms/regexmatcher_v2_ct.cpp) calls too.
#include <string>

#include "arms/rm_arm.hpp"
#include "arms/rm_v2.hpp"

#ifndef RB_REGEXMATCHER_COMMIT
#define RB_REGEXMATCHER_COMMIT "unknown"
#endif

[[gnu::noinline]] matcher::route::Match rb::rm::find_v2(const matcher::route::TableView& view, unsigned method,
                                                       std::string_view path) {
    return matcher::route::find(view, method, path);
}

namespace {

struct Info {
    static rb::ArmInfo info() {
        return {"regexmatcher-v2",
                std::string("RegexMatcher v2 ") + std::string(RB_REGEXMATCHER_COMMIT).substr(0, 9) + " (table built at run time)",
                "views into the path"};
    }
};

using RegexMatcherV2Arm = rb::rm::Arm<rb::rm::V2, rb::rm::RunTime<rb::rm::V2>, Info>;

}  // namespace

RB_ARM(RegexMatcherV2Arm)
