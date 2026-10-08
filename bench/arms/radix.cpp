// In-repo baseline: a radix tree over path segments, one per method. Each node has its
// literal children sorted by label (binary search), at most one parameter child and at most
// one catch-all child. A literal child is tried before the parameter child, and the
// parameter child before the catch-all; a failed branch backtracks. Captures are views into
// the query path; a lookup allocates nothing.
#include <algorithm>
#include <map>
#include <string>
#include <string_view>
#include <vector>

#include "core/runner.hpp"

namespace {

using namespace rb;

class RadixArm final {
public:
    static ArmInfo info() { return {"radix", "in-repo", "views into the path"}; }

    RadixArm() : build_(kMethods) {}

    void add(const Route& r, RouteId id) {
        auto node = static_cast<std::int32_t>(r.method);
        for (const Segment& s : r.segs) {
            std::int32_t next = -1;
            if (s.kind == Seg::Literal) {
                const auto it = build_[node].lit.find(s.text);
                next = it == build_[node].lit.end() ? -1 : it->second;
                if (next < 0) {
                    next = fresh();
                    build_[node].lit.emplace(s.text, next);
                }
            } else {
                std::int32_t& slot = s.kind == Seg::Param ? build_[node].param : build_[node].rest;
                if (slot < 0) {
                    const std::int32_t n = fresh();  // may reallocate build_, so assign after
                    (s.kind == Seg::Param ? build_[node].param : build_[node].rest) = n;
                }
                next = s.kind == Seg::Param ? build_[node].param : build_[node].rest;
            }
            node = next;
        }
        if (build_[node].id == kNoRoute) {
            build_[node].id = id;  // the first registered of two identical routes wins
        }
    }

    void finalize() {
        nodes_.resize(build_.size());
        for (std::size_t i = 0; i < build_.size(); ++i) {
            Node& n = nodes_[i];
            n.kid_begin = static_cast<std::uint32_t>(kid_node_.size());
            n.kid_count = static_cast<std::uint32_t>(build_[i].lit.size());
            n.param = build_[i].param;
            n.rest = build_[i].rest;
            n.id = build_[i].id;
            for (const auto& [label, kid] : build_[i].lit) {
                labels_.push_back(label);
                kid_node_.push_back(kid);
            }
        }
        kid_label_.assign(labels_.begin(), labels_.end());  // views, now that labels_ is final
        build_.clear();
        build_.shrink_to_fit();
    }

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        c.n = 0;
        RouteId out = kNoRoute;
        if (path.empty() || path.front() != '/' ||
            !descend(static_cast<std::int32_t>(m), path, 1, c, out)) {
            c.n = 0;
            return kNoRoute;
        }
        return out;
    }

private:
    struct Build {
        std::map<std::string, std::int32_t, std::less<>> lit;
        std::int32_t param = -1;
        std::int32_t rest = -1;
        RouteId id = kNoRoute;
    };
    struct Node {
        std::uint32_t kid_begin = 0;
        std::uint32_t kid_count = 0;
        std::int32_t param = -1;
        std::int32_t rest = -1;
        RouteId id = kNoRoute;
    };

    std::int32_t fresh() {
        build_.emplace_back();
        return static_cast<std::int32_t>(build_.size() - 1);
    }

    // pos is the index of the next segment's first byte, or path.size() + 1 at the end.
    bool descend(std::int32_t at, std::string_view path, std::size_t pos, Captures& c, RouteId& out) const {
        const Node& n = nodes_[static_cast<std::size_t>(at)];
        if (pos > path.size()) {
            out = n.id;
            return n.id != kNoRoute;
        }
        const std::size_t slash = path.find('/', pos);
        const std::size_t end = slash == std::string_view::npos ? path.size() : slash;
        const std::string_view seg = path.substr(pos, end - pos);
        if (seg.empty()) {
            return false;
        }
        const auto first = kid_label_.begin() + n.kid_begin;
        const auto last = first + n.kid_count;
        const auto it = std::lower_bound(first, last, seg);
        if (it != last && *it == seg &&
            descend(kid_node_[static_cast<std::size_t>(it - kid_label_.begin())], path, end + 1, c, out)) {
            return true;
        }
        if (n.param >= 0 && c.n < kMaxParams) {
            c.v[c.n++] = seg;
            if (descend(n.param, path, end + 1, c, out)) {
                return true;
            }
            --c.n;
        }
        if (n.rest >= 0 && c.n < kMaxParams) {
            const RouteId id = nodes_[static_cast<std::size_t>(n.rest)].id;
            if (id != kNoRoute) {
                c.v[c.n++] = path.substr(pos);
                out = id;
                return true;
            }
        }
        return false;
    }

    std::vector<Build> build_;
    std::vector<Node> nodes_;
    std::vector<std::string> labels_;
    std::vector<std::string_view> kid_label_;
    std::vector<std::int32_t> kid_node_;
};

}  // namespace

RB_ARM(RadixArm)
