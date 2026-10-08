// RegexMatcher v2's compile-time table copied into a heap block: an exploratory arm, built only
// when RB_ARMS names it (hypotheses-round2.md, section 7, last item; design/round2/engineering.md,
// 3.4). It finds the compile-time table of bench/gen that holds its routes, as the
// regexmatcher-v2-ct arm does, in that arm's registry (arms/regexmatcher_v2_ct.cpp), and copies
// the table's bytes, in their own layout, into one block of the heap aligned to a page
// (kPageAlign). Every element then lies at the same offset into a page as in the compile-time
// table and in the run-time table. What differs from the compile-time arm is where the bytes
// are (the heap, not the binary); what differs from the run-time arm is only that the bytes were
// copied, not built. It is the adapter of the other two arms (arms/rm_arm.hpp), so its lookup is
// the same call of rb::rm::find_v2. The search by digest is repeated here, not shared, so that
// the files the measured arms compile stay as their sanitizer records compiled them.
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <new>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>

#include "arms/ct_registry.hpp"
#include "arms/rm_arm.hpp"
#include "arms/rm_v2.hpp"

#ifndef RB_REGEXMATCHER_COMMIT
#define RB_REGEXMATCHER_COMMIT "unknown"
#endif

namespace {

namespace route = matcher::route;

class HeapCopy {
public:
    HeapCopy() = default;
    HeapCopy(const HeapCopy&) = delete;
    HeapCopy& operator=(const HeapCopy&) = delete;
    ~HeapCopy() { release(); }

    void add(const rb::Route& r, rb::RouteId id) {
        if (id != count_) {
            throw rb::Refused("regexmatcher-v2-ct-heap: route ids must be registered in order");
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
                return copy(e.view);
            }
        }
        throw rb::Refused("regexmatcher-v2-ct-heap: no compile-time table in bench/gen holds these routes (generated "
                          "for m <= 1000 and the table seeds of rbench's kTableSeeds)");
    }

private:
    // The compile-time table's object, from the start of its first array to the end of its arena,
    // copied byte for byte into a block aligned to a page. The arena is never empty (it holds one
    // byte more than its labels), so the object's start is found from it.
    route::TableView copy(const route::TableView& v) {
        const route::TableLayout l =
            route::table_layout({v.nodes.size(), v.edges.size(), v.literals.size(), v.arena.size()});
        const std::byte* base = reinterpret_cast<const std::byte*>(v.arena.data()) - l.arena;
        block_ = static_cast<std::byte*>(::operator new(l.bytes, std::align_val_t{route::kPageAlign}));
        std::memcpy(block_, base, l.bytes);
        route::TableView out = v;  // the roots and the method masks are values
        out.nodes = rebase(v.nodes, base, l.nodes);
        out.edges = rebase(v.edges, base, l.edges);
        out.literals = rebase(v.literals, base, l.literals);
        out.arena = std::string_view(reinterpret_cast<const char*>(block_ + l.arena), v.arena.size());
        return out;
    }

    // An array of the copy; an empty array gets an empty span, as in RuntimeTable.
    template <class T>
    std::span<const T> rebase(std::span<const T> s, const std::byte* base, std::size_t at) const {
        if (s.empty()) {
            return {};
        }
        if (reinterpret_cast<const std::byte*>(s.data()) != base + at) {
            throw std::logic_error("regexmatcher-v2-ct-heap: a compile-time table's array is not where table_layout puts it");
        }
        return {std::launder(reinterpret_cast<const T*>(block_ + at)), s.size()};
    }

    void release() noexcept {
        if (block_ != nullptr) {
            ::operator delete(block_, std::align_val_t{route::kPageAlign});
        }
        block_ = nullptr;
    }

    std::string lines_;
    std::uint32_t count_ = 0;
    std::byte* block_ = nullptr;
};

struct Info {
    static rb::ArmInfo info() {
        return {"regexmatcher-v2-ct-heap",
                std::string("RegexMatcher v2 ") + std::string(RB_REGEXMATCHER_COMMIT).substr(0, 9) +
                    " (compile-time table copied into a heap block)",
                "views into the path"};
    }
};

using RegexMatcherV2CtHeapArm = rb::rm::Arm<rb::rm::V2, HeapCopy, Info>;

}  // namespace

RB_ARM(RegexMatcherV2CtHeapArm)
