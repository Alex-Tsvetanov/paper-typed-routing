// The adversarial tool's counting copy (tools/route_count.hpp): the table built by the copy's own
// build_table, the lookup through the copy's find with a Counter set, and the nodes of each method's
// trie (every node reachable from its root), for the bound. Untimed.
#include <algorithm>
#include <array>
#include <span>
#include <string>
#include <vector>

#include "tools/adversarial.hpp"
#include "tools/route_count.hpp"

namespace adv {
namespace {

namespace R = matcher::route_count;

std::uint64_t reachable(const R::TableView& v, std::uint32_t root) {
    std::uint64_t n = 0;
    std::vector<std::uint32_t> todo{root};
    while (!todo.empty()) {
        const R::Node& node = v.nodes[todo.back()];
        todo.pop_back();
        ++n;
        for (std::uint32_t i = node.edges; i < node.edges + node.count; ++i) {
            if (v.edges[i].child != R::kNone) {
                todo.push_back(v.edges[i].child);
            }
        }
        for (const std::uint32_t k : {node.u64, node.i64, node.param, node.rest}) {
            if (k != R::kNone) {
                todo.push_back(k);
            }
        }
    }
    return n;
}

// The counts of one lookup, kept per node as well (entries and resumptions), and walk by walk
// against the nodes of the trie walked.
class Tally final : public R::Counter {
public:
    Tally(std::size_t nodes, const std::array<std::uint64_t, R::kMethodSlots>& trie,
          const std::array<std::uint32_t, R::kMethodSlots>& roots)
        : entered_(nodes), resumed_(nodes), trie_(trie), roots_(roots) {}

    void reset() {
        std::fill(entered_.begin(), entered_.end(), 0u);
        std::fill(resumed_.begin(), resumed_.end(), 0u);
        c_ = {};
        walk_nodes_ = 0;
        walk_entries_ = 0;
    }

    Counts done() {
        close();
        return c_;
    }

    void walk(std::uint32_t root) noexcept override {
        close();
        walk_nodes_ = 0;
        for (std::size_t m = 0; m < roots_.size(); ++m) {
            walk_nodes_ = roots_[m] == root ? trie_[m] : walk_nodes_;
        }
        walk_entries_ = 0;
        ++c_.walks;
        c_.walked_nodes += walk_nodes_;
    }

    void visit(std::uint32_t node, std::uint8_t stage) noexcept override {
        if (stage == 0) {
            ++c_.entries;
            ++walk_entries_;
            c_.max_entries = std::max(c_.max_entries, ++entered_[node]);
        } else {
            ++c_.resumptions;
            c_.max_resumptions = std::max(c_.max_resumptions, ++resumed_[node]);
        }
    }

    void push(std::uint32_t, std::size_t depth) noexcept override {
        ++c_.pushed;
        c_.deepest = std::max(c_.deepest, static_cast<std::uint32_t>(depth));
    }

    void pop(std::uint32_t, std::size_t) noexcept override { ++c_.popped; }

private:
    void close() {
        c_.each_walk_within = c_.each_walk_within && walk_entries_ <= walk_nodes_;
        walk_entries_ = 0;
    }

    std::vector<std::uint32_t> entered_;
    std::vector<std::uint32_t> resumed_;
    std::array<std::uint64_t, R::kMethodSlots> trie_;
    std::array<std::uint32_t, R::kMethodSlots> roots_;
    Counts c_;
    std::uint64_t walk_nodes_ = 0;
    std::uint64_t walk_entries_ = 0;
};

}  // namespace

struct Counting::Impl {
    R::Built table;
    std::array<std::uint64_t, R::kMethodSlots> trie{};
    std::unique_ptr<Tally> tally;
};

Counting::Counting(const Table& t) : impl_(std::make_unique<Impl>()) {
    std::vector<R::RouteSpec> specs;
    specs.reserve(t.patterns.size());
    for (std::size_t i = 0; i < t.patterns.size(); ++i) {
        specs.push_back({t.methods[i], t.patterns[i], static_cast<std::uint32_t>(i)});
    }
    impl_->table = R::build_table(specs);
    if (!ok()) {
        return;
    }
    const R::TableView v = impl_->table.view();
    for (std::size_t m = 0; m < R::kMethodSlots; ++m) {
        impl_->trie[m] = v.roots[m] == R::kNone ? 0 : reachable(v, v.roots[m]);
    }
    impl_->tally = std::make_unique<Tally>(v.nodes.size(), impl_->trie, v.roots);
}

Counting::~Counting() = default;

bool Counting::ok() const { return impl_->table.error == R::BuildError::None; }

std::size_t Counting::nodes() const { return ok() ? impl_->table.nodes.size() : 0; }

std::uint64_t Counting::trie_nodes(unsigned method) const {
    return method < R::kMethodSlots ? impl_->trie[method] : 0;
}

Answer Counting::find(const Request& r, Counts& c) {
    impl_->tally->reset();
    R::counter = impl_->tally.get();
    const R::Match m = R::find(impl_->table.view(), r.method, r.path);
    R::counter = nullptr;
    c = impl_->tally->done();
    Answer a{static_cast<int>(m.status), m.route, m.allowed, {}};
    for (const R::Capture& v : m.values()) {
        a.values.emplace_back(v.view());
    }
    return a;
}

}  // namespace adv
