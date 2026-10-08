// In-repo baseline: one exact-match hash table per method, keyed by the whole path. It holds
// literal routes only, so it is the lower bound for static tables and absent for the others.
// Heterogeneous lookup, so a lookup allocates nothing.
#include <array>
#include <functional>
#include <string>
#include <string_view>
#include <unordered_map>

#include "core/runner.hpp"

namespace {

using namespace rb;

struct ViewHash {
    using is_transparent = void;
    std::size_t operator()(std::string_view s) const noexcept { return std::hash<std::string_view>{}(s); }
};

class HashArm final {
public:
    static ArmInfo info() { return {"hash", "in-repo", "none (literal routes only)"}; }

    void add(const Route& r, RouteId id) {
        for (const Segment& s : r.segs) {
            if (s.kind != Seg::Literal) {
                throw Refused("hash: an exact-match table holds literal routes only");
            }
        }
        maps_[static_cast<std::size_t>(r.method)].emplace(render(r), id);
    }

    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        c.n = 0;
        const auto& map = maps_[static_cast<std::size_t>(m)];
        const auto it = map.find(std::string_view(path));
        return it == map.end() ? kNoRoute : it->second;
    }

private:
    std::array<std::unordered_map<std::string, RouteId, ViewHash, std::equal_to<>>, kMethods> maps_;
};

}  // namespace

RB_ARM(HashArm)
