// Crow's router trie (crow::Trie), one per method as crow::Router keeps them. A parameter is
// <string> (one non-empty segment) and a catch-all <path> (the rest of the URL). Rule index
// 0 means no match, so route id k is added as rule k + 1; of two full matches the lower
// rule index wins. validate() compresses the trie once after the last route. find() returns
// the captured values as std::string copies in routing_params::string_params; the arm keeps
// the last result so its views stay valid.
#include <crow/logging.h>
#include <crow/routing.h>

#include <array>
#include <string>

#include "core/runner.hpp"

namespace {

using namespace rb;

class CrowArm final {
public:
    static ArmInfo info() { return {"crow", "CrowCpp/Crow v1.3.4 (asio 1.38.2 headers)", "std::string copies per match"}; }

    CrowArm() { crow::logger::setLogLevel(crow::LogLevel::Warning); }

    void add(const Route& r, RouteId id) {
        std::string rule;
        for (const Segment& s : r.segs) {
            rule += '/';
            rule += s.kind == Seg::Literal ? s.text : (s.kind == Seg::Param ? "<string>" : "<path>");
        }
        const auto m = static_cast<std::size_t>(r.method);
        try {
            tries_[m].add(rule, static_cast<std::size_t>(id) + 1);
        } catch (const std::exception& e) {
            throw Refused(std::string("crow: ") + e.what());
        }
        used_[m] = true;
    }

    void finalize() {
        for (std::size_t m = 0; m < kMethods; ++m) {
            if (used_[m]) {
                tries_[m].validate();
            }
        }
    }

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        c.n = 0;
        last_ = tries_[static_cast<std::size_t>(m)].find(path);
        if (last_.rule_index == 0) {
            return kNoRoute;
        }
        for (const std::string& v : last_.r_params.string_params) {
            if (c.n < kMaxParams) {
                c.v[c.n++] = v;
            }
        }
        return static_cast<RouteId>(last_.rule_index - 1);
    }

private:
    std::array<crow::Trie, kMethods> tries_{};
    std::array<bool, kMethods> used_{};
    crow::routing_handle_result last_;
};

}  // namespace

RB_ARM(CrowArm)
