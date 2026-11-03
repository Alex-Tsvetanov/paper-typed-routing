// The adversarial tool's cells (design/review-runs/adversarial.md): the tables, their queries and
// what each query must return, the pinned code and the counting copy behind one interface each,
// and the checks of the written bound. Shared by tools/adversarial.cpp and tools/test_adversarial.cpp.
//
// Two families of tables, each route k segments and one last literal, all combinations of the
// segment kinds, registered under GET and under PUT:
//   two-kinds   each segment the literal "a" or a plain parameter, k = 1, 2, 4, 8, 12, 16
//   four-kinds  each segment the literal "1", an unsigned integer, a signed integer or a plain
//               parameter, k = 1, 2, 4, 6, 8
// The all-parameter route ends in "all", every other route in "end". With catch_all, one more
// route "/{*rest}" per method. Three queries: miss (k segments, then "miss", under GET), last-hit
// (the same, then "all"), other-method (the miss path under DELETE, which has no route).
#pragma once

#include <array>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <string>
#include <type_traits>
#include <vector>

namespace adv {

// v2's method indices (matcher::route::find).
inline constexpr unsigned kGet = 0;
inline constexpr unsigned kPut = 2;
inline constexpr unsigned kDelete = 3;
inline constexpr std::uint32_t kNone = 0xFFFF'FFFFu;
// The written bound: a walk resumes a node at most once after each kind of child it tried.
inline constexpr std::uint32_t kMaxResumptions = 4;

enum class Family : std::uint8_t { Two, Four };
enum class Query : std::uint8_t { Miss, LastHit, OtherMethod };
inline constexpr Query kQueries[] = {Query::Miss, Query::LastHit, Query::OtherMethod};

struct TableSpec {
    Family family = Family::Two;
    unsigned depth = 1;
    bool catch_all = false;
};

struct Table {
    TableSpec spec;
    std::vector<std::string> patterns;  // registration order; a route's value is its index
    std::vector<unsigned> methods;
    std::uint32_t all_param = kNone;    // GET's all-parameter route
    std::uint32_t catch_all = kNone;    // GET's catch-all route, if any
    std::string digest;                 // sha256 of "<method> <pattern>\n" per route, in order
};

struct Request {
    unsigned method = kGet;
    std::string path;
};

// One lookup's result, as matcher::route::Match has it: status 0 found, 1 method not allowed,
// 2 not found; the route (kNone unless found); the methods that match (with 1); the values.
struct Answer {
    int status = 2;
    std::uint32_t route = kNone;
    std::uint16_t allowed = 0;
    std::vector<std::string> values;
    bool operator==(const Answer&) const = default;
};

// What the counting copy's walks did in one lookup (tools/route_count.hpp, Counter).
struct Counts {
    std::uint64_t entries = 0;          // passes of the walk's loop at stage 0: nodes entered
    std::uint64_t resumptions = 0;      // passes at a later stage: nodes resumed after a pop
    std::uint64_t pushed = 0;           // choice points pushed
    std::uint64_t popped = 0;           // choice points popped: the backtracks
    std::uint32_t deepest = 0;          // the deepest choice stack
    std::uint32_t max_entries = 0;      // the most entries of one node in one walk
    std::uint32_t max_resumptions = 0;  // the most resumptions of one node in one walk
    std::uint32_t walks = 0;            // tries walked (one per method looked up)
    std::uint64_t walked_nodes = 0;     // the nodes of those tries, summed
    bool each_walk_within = true;       // every walk entered at most as many nodes as its trie has
};

struct Cell {
    std::string id;
    TableSpec table;
    Query query = Query::Miss;
};

std::string family_name(Family f);
std::string query_name(Query q);
std::string table_id(const TableSpec& s);
std::vector<unsigned> depths(Family f);
std::vector<TableSpec> table_specs();  // the 22 tables
std::vector<Cell> cells();             // the 44 cells: every query on the 11 tables, miss on the 11 with catch_all
Table make_table(const TableSpec& s);
Request request(const Table& t, Query q);
Answer expected(const Table& t, Query q);
// The walks a query must make: one when its own method finds a route (the catch-all included),
// else one per method that has routes (GET's miss walks GET then PUT, DELETE walks GET and PUT).
std::uint32_t expected_walks(const Table& t, Query q);
std::string answer_text(const Answer& a);

// A built table as bytes: every field of every node, edge and exact-match slot, the label arena,
// the roots and the method masks. Compared byte for byte between the pinned build and the copy's,
// whose structs are laid out alike. An edge has 4 bytes of tail padding, which a build leaves
// indeterminate, so its fields are copied one by one and the padding is not compared.
struct Image {
    std::vector<unsigned char> nodes;
    std::vector<unsigned char> edges;
    std::vector<unsigned char> literals;
    std::vector<unsigned char> arena;
    std::array<std::uint32_t, 9> roots{};
    std::uint16_t methods = 0;
    std::uint16_t literal_methods = 0;
    bool operator==(const Image&) const = default;
};

namespace detail {

template <class T>
void append_bytes(std::vector<unsigned char>& out, const T& v) {
    static_assert(std::is_trivially_copyable_v<T>);
    const auto* p = reinterpret_cast<const unsigned char*>(&v);
    out.insert(out.end(), p, p + sizeof(T));
}

}  // namespace detail

// The image of a TableView of either code (matcher::route or matcher::route_count).
template <class View>
Image image_of(const View& v) {
    using Node = std::remove_cvref_t<decltype(v.nodes[0])>;
    using Slot = std::remove_cvref_t<decltype(v.literals[0])>;
    static_assert(std::has_unique_object_representations_v<Node>, "a node has padding");
    static_assert(std::has_unique_object_representations_v<Slot>, "a literal slot has padding");
    Image im;
    for (const auto& n : v.nodes) {
        detail::append_bytes(im.nodes, n);
    }
    for (const auto& e : v.edges) {
        detail::append_bytes(im.edges, e.word);
        detail::append_bytes(im.edges, e.child);
        detail::append_bytes(im.edges, e.off);
        detail::append_bytes(im.edges, e.len);
    }
    for (const auto& s : v.literals) {
        detail::append_bytes(im.literals, s);
    }
    im.arena.assign(v.arena.begin(), v.arena.end());
    for (std::size_t i = 0; i < im.roots.size(); ++i) {
        im.roots[i] = v.roots[i];
    }
    im.methods = v.methods;
    im.literal_methods = v.literal_methods;
    return im;
}

// The first part in which two images differ ("nodes", "edges", ...), or nullptr if they are equal.
const char* first_difference(const Image& a, const Image& b);

// RegexMatcher v2 at the pinned commit, unmodified, built and looked up as the regexmatcher-v2
// arm does: make_runtime_table, and the out-of-line rb::rm::find_v2 (tools/adversarial_pinned.cpp).
class Pinned {
public:
    explicit Pinned(const Table& t);
    ~Pinned();
    bool ok() const;
    std::size_t nodes() const;
    Image image() const;
    Answer find(const Request& r) const;  // a table that did not build answers like an empty one

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

// The counting copy (tools/route_count.hpp; tools/adversarial_count.cpp).
class Counting {
public:
    explicit Counting(const Table& t);
    ~Counting();
    bool ok() const;
    std::size_t nodes() const;
    Image image() const;
    std::uint64_t trie_nodes(unsigned method) const;  // nodes reachable from the method's root; 0 if none
    // A table that did not build counts nothing (c zeroed) and answers like an empty one, so that
    // check() fails on it.
    Answer find(const Request& r, Counts& c);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

// The deterministic checks of one query (design/review-runs/adversarial.md, "What is decided").
// The last four keep a broken count from passing the bounds vacuously: a count of zero entries, of
// walks or of resumptions satisfies every "at most".
struct Check {
    bool expected_answer = false;    // the pinned code answers what the table was built to answer
    bool same_answer = false;        // the counting copy answers as the pinned code
    bool bound_entries = false;      // entries at most the nodes of the tries walked, walk by walk
    bool bound_resumptions = false;  // at most kMaxResumptions resumptions of any node
    bool counted = false;            // at least one entry was counted
    bool pops_resume = false;        // every pop is a resumption, and pops are at most pushes
    bool entered_once = false;       // no node was entered twice within one walk
    bool walks_as_expected = false;  // the walks are as many as the query must make
    bool ok() const {
        return expected_answer && same_answer && bound_entries && bound_resumptions && counted && pops_resume &&
               entered_once && walks_as_expected;
    }
};
// walks is expected_walks(table, query).
Check check(const Answer& want, const Answer& pinned, const Answer& copy, const Counts& c, std::uint32_t walks);

// Every query of every table through both codes; one line per query to out. Returns the failures.
int self_test(std::FILE* out);

}  // namespace adv
