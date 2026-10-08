// table_digest: the table RegexMatcher v2 builds at run time for the paper's tables, as digests,
// so that a change to the build can be shown to leave every table byte for byte the same
// (design/round2/engineering.md, target (a), adoption rule 1). The table is built as the
// regexmatcher-v2 arm builds it: make_runtime_table where the library has it (C2), build_table
// before. Per shape and size: the sha256 of the table's contents (every field of every node,
// edge and exact-match slot, the label arena, the roots and the method sets; field by field, so
// padding never counts; an edge's chain, Edge::tail (B1), and a node's chain length,
// Node::chain (B1'), only where they are not 0, so that a table without chains keeps the digest
// it had before chains existed), the arrays' lengths, the heap allocations and bytes that build
// made, and the number of chained edges (B1) and of chain nodes (B1').
//
//     table_digest [--seed N] [--sizes 10,100,...]      (default: seed 1, 10 to 100,000)
//
// Built from bench/core and RegexMatcher's include directory (bench/tools/CMakeLists.txt,
// REGEXMATCHER_DIR), with no arm and no fetched code.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "core/table.hpp"

namespace {
bool g_count = false;
std::uint64_t g_allocs = 0;
std::uint64_t g_bytes = 0;
}  // namespace

void* operator new(std::size_t n) {
    if (g_count) {
        ++g_allocs;
        g_bytes += n;
    }
    if (void* p = std::malloc(n ? n : 1)) {
        return p;
    }
    throw std::bad_alloc();
}
void* operator new(std::size_t n, std::align_val_t a) {
    if (g_count) {
        ++g_allocs;
        g_bytes += n;
    }
    const std::size_t al = static_cast<std::size_t>(a);
    if (void* p = std::aligned_alloc(al, (n + al - 1) / al * al)) {
        return p;
    }
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete(void* p, std::align_val_t) noexcept { std::free(p); }
void operator delete(void* p, std::size_t, std::align_val_t) noexcept { std::free(p); }

#include <matcher/route.hpp>

namespace {

namespace R = matcher::route;

struct Hasher {
    std::string bytes;
    template <class T>
    void put(T v) {
        char b[sizeof(T)];
        std::memcpy(b, &v, sizeof(T));
        bytes.append(b, sizeof(T));
    }
};

// An edge's chain (Edge::tail, from B1 on), or 0 where the library has no chains.
template <class E>
std::uint32_t tail_of(const E& e) {
    if constexpr (requires { e.tail; }) {
        return e.tail;
    } else {
        return 0;
    }
}

// A node's chain length (Node::chain, from B1' on), or 0 where the library has no chain nodes.
template <class N>
std::uint32_t chain_of(const N& n) {
    if constexpr (requires { n.chain; }) {
        return n.chain;
    } else {
        return 0;
    }
}

// Whether a node is a chain node (kind 2 in a library whose nodes have Node::chain, B1').
template <class N>
bool is_chain_node(const N& n) {
    if constexpr (requires { n.chain; }) {
        return n.hashed == 2;
    } else {
        return false;
    }
}

std::string digest(const R::TableView& v) {
    Hasher h;
    h.put<std::uint64_t>(v.nodes.size());
    for (const R::Node& n : v.nodes) {
        h.put(n.edges);
        h.put(n.count);
        h.put(n.hashed);
        h.put(n.branches);
        h.put(n.u64);
        h.put(n.i64);
        h.put(n.param);
        h.put(n.rest);
        h.put(n.route);
        if (const std::uint32_t chain = chain_of(n); chain != 0) {
            h.put(chain);  // only in a chain node: a table without chains keeps its digest
        }
    }
    h.put<std::uint64_t>(v.edges.size());
    for (const R::Edge& e : v.edges) {
        h.put(e.word);
        h.put(e.child);
        h.put(e.off);
        h.put(e.len);
        if (const std::uint32_t tail = tail_of(e); tail != 0) {
            h.put(tail);  // only where there is a chain: a table without chains keeps its digest
        }
    }
    h.put<std::uint64_t>(v.literals.size());
    for (const R::LiteralSlot& s : v.literals) {
        h.put(s.hash);
        h.put(s.off);
        h.put(s.len);
        h.put(s.route);
        h.put(s.method);
    }
    h.put<std::uint64_t>(v.arena.size());
    h.bytes.append(v.arena.data(), v.arena.size());
    for (const std::uint32_t r : v.roots) {
        h.put(r);
    }
    h.put(v.methods);
    h.put(v.literal_methods);
    return rb::sha256_hex(h.bytes);
}

// The table as the regexmatcher-v2 arm builds it: make_runtime_table (one page-aligned block)
// where the library has it, build_table before that (commits before C2). The unqualified call
// is found by argument-dependent lookup in matcher::route, or not at all.
template <class Specs>
concept HasRuntimeTable = requires(Specs s) { make_runtime_table(s); };

template <class Specs>
auto build(Specs specs) {
    if constexpr (HasRuntimeTable<Specs>) {
        return make_runtime_table(specs);
    } else {
        return R::build_table(specs);
    }
}

std::vector<std::string> split(const std::string& s) {
    std::vector<std::string> out;
    std::size_t pos = 0;
    while (pos <= s.size()) {
        const std::size_t c = s.find(',', pos);
        const std::size_t e = c == std::string::npos ? s.size() : c;
        if (e > pos) {
            out.push_back(s.substr(pos, e - pos));
        }
        pos = e + 1;
    }
    return out;
}

}  // namespace

int main(int argc, char** argv) {
    std::uint64_t seed = 1;
    std::string sizes = "10,100,1000,10000,100000";
    for (int i = 1; i + 1 < argc; i += 2) {
        const std::string k = argv[i];
        if (k == "--seed") {
            seed = std::strtoull(argv[i + 1], nullptr, 10);
        } else if (k == "--sizes") {
            sizes = argv[i + 1];
        } else {
            std::fprintf(stderr, "usage: table_digest [--seed N] [--sizes 10,100,...]\n");
            return 2;
        }
    }
    std::printf("shape\tm\tseed\tdigest\tnodes\tedges\tliterals\tarena\tbuild_allocs\tbuild_alloc_bytes\tchained_edges\tchain_nodes\n");
    std::vector<std::pair<rb::Shape, std::uint32_t>> tables;
    for (const std::string& m : split(sizes)) {
        for (rb::Shape sh : rb::kShapes) {
            tables.emplace_back(sh, static_cast<std::uint32_t>(std::stoul(m)));
        }
    }
    tables.emplace_back(rb::Shape::Github, rb::kGithubRoutes);
    for (const auto& [sh, m] : tables) {
        const rb::Table t = rb::generate_table({sh, m, seed, 1});
        std::vector<std::string> patterns;
        std::vector<R::RouteSpec> specs;
        patterns.reserve(t.routes.size());
        for (const rb::Route& r : t.routes) {
            patterns.push_back(rb::render(r));
        }
        for (std::uint32_t i = 0; i < t.routes.size(); ++i) {
            specs.push_back({static_cast<unsigned>(t.routes[i].method), patterns[i], i});
        }
        g_allocs = g_bytes = 0;
        g_count = true;
        auto b = build(std::span<const R::RouteSpec>(specs));
        g_count = false;
        if (b.error != R::BuildError::None) {
            std::fprintf(stderr, "table_digest: %s m=%u does not build\n", std::string(rb::shape_name(sh)).c_str(), m);
            return 1;
        }
        const R::TableView v = b.view();
        std::size_t chained = 0;
        for (const R::Edge& e : v.edges) {
            chained += tail_of(e) != 0;
        }
        std::size_t chain_nodes = 0;
        for (const R::Node& n : v.nodes) {
            chain_nodes += is_chain_node(n);
        }
        std::printf("%s\t%u\t%llu\t%s\t%zu\t%zu\t%zu\t%zu\t%llu\t%llu\t%zu\t%zu\n", std::string(rb::shape_name(sh)).c_str(),
                    static_cast<unsigned>(t.routes.size()), static_cast<unsigned long long>(t.spec.seed),
                    digest(v).c_str(), v.nodes.size(), v.edges.size(), v.literals.size(), v.arena.size(),
                    static_cast<unsigned long long>(g_allocs), static_cast<unsigned long long>(g_bytes), chained,
                    chain_nodes);
    }
    return 0;
}
