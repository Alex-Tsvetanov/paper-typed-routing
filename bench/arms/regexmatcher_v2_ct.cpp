// RegexMatcher v2's table as a compile-time constant (the arm of H7): the tables of bench/gen/
// are constexpr objects built by matcher::route::make_static_table while this binary was
// compiled, one per shape at m = 10, 100 and 1,000 and per table seed of rbench's kTableSeeds,
// and the GitHub table. The arm is given the routes like every arm, checks that a compiled
// table holds exactly those routes (by the table digest), and refuses the table otherwise. It is
// the adapter of the run-time arm (arms/rm_arm.hpp) with another source of the view, so its
// lookup is the same call of rb::rm::find_v2.
#include <string>

#include "arms/ct_registry.hpp"
#include "arms/rm_arm.hpp"
#include "arms/rm_v2.hpp"

#ifndef RB_REGEXMATCHER_COMMIT
#define RB_REGEXMATCHER_COMMIT "unknown"
#endif

std::vector<rb::ct::Entry>& rb::ct::registry() {
    static std::vector<Entry> entries;
    return entries;
}

namespace {

class CompileTime {
public:
    void add(const rb::Route& r, rb::RouteId id) {
        if (id != count_) {
            throw rb::Refused("regexmatcher-v2-ct: route ids must be registered in order");
        }
        ++count_;
        lines_ += rb::method_name(r.method);
        lines_ += ' ';
        lines_ += rb::render(r);
        lines_ += '\n';
    }

    template <class L>
    typename L::TableView finalize() {
        const std::string digest = rb::sha256_hex(lines_);
        lines_ = {};
        for (const rb::ct::Entry& e : rb::ct::registry()) {
            if (e.digest == digest && e.routes == count_) {
                return e.view;
            }
        }
        throw rb::Refused("regexmatcher-v2-ct: no compile-time table in bench/gen holds these routes (generated for "
                          "m <= 1000 and the table seeds of rbench's kTableSeeds)");
    }

private:
    std::string lines_;
    std::uint32_t count_ = 0;
};

struct Info {
    static rb::ArmInfo info() {
        return {"regexmatcher-v2-ct",
                std::string("RegexMatcher v2 ") + std::string(RB_REGEXMATCHER_COMMIT).substr(0, 9) +
                    " (table built while compiling)",
                "views into the path"};
    }
};

using RegexMatcherV2CtArm = rb::rm::Arm<rb::rm::V2, CompileTime, Info>;

}  // namespace

RB_ARM(RegexMatcherV2CtArm)
