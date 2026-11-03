// The adversarial tool's pinned code: RegexMatcher v2 at the pinned commit, unmodified, through the
// regexmatcher-v2 arm's Lib (arms/rm_v2.hpp): make_runtime_table, and rb::rm::find_v2 compiled out
// of line here as arms/regexmatcher_v2.cpp compiles it. The timed loop (tools/adversarial.cpp) and
// the checks call this one copy of the lookup.
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "arms/rm_v2.hpp"
#include "tools/adversarial.hpp"

[[gnu::noinline]] matcher::route::Match rb::rm::find_v2(const matcher::route::TableView& view, unsigned method,
                                                       std::string_view path) {
    return matcher::route::find(view, method, path);
}

namespace adv {

struct Pinned::Impl {
    rb::rm::V2::Built table;
};

Pinned::Pinned(const Table& t) : impl_(std::make_unique<Impl>()) {
    std::vector<matcher::route::RouteSpec> specs;
    specs.reserve(t.patterns.size());
    for (std::size_t i = 0; i < t.patterns.size(); ++i) {
        specs.push_back({t.methods[i], t.patterns[i], static_cast<std::uint32_t>(i)});
    }
    impl_->table = rb::rm::V2::build(specs);
}

Pinned::~Pinned() = default;

bool Pinned::ok() const { return impl_->table.error == rb::rm::V2::kBuildOk; }

std::size_t Pinned::nodes() const { return ok() ? impl_->table.view().nodes.size() : 0; }

Answer Pinned::find(const Request& r) const {
    const matcher::route::Match m = rb::rm::V2::find(impl_->table.view(), r.method, r.path);
    Answer a{static_cast<int>(m.status), m.route, m.allowed, {}};
    for (const matcher::route::Capture& c : m.values()) {
        a.values.emplace_back(c.view());
    }
    return a;
}

}  // namespace adv
