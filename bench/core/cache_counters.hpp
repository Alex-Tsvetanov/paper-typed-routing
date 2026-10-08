// Memory-side hardware counters for a cell: L1 data cache misses, L2 misses of data
// requests, L1 data TLB misses and dispatch-resource stalls, counted over whole passes of the
// ring after the timed epochs (nanobench programs cycles, instructions, branches and branch
// misses there).
//
// A Zen 3 core has six counters, and the kernel's NMI watchdog holds one, so a group of five
// is the most that is scheduled whole. The events are counted in groups, one after the other,
// each over its own passes, each with cycles as its leader:
//   memory     cycles, l1d_misses, l2_misses, dtlb_misses
//   ae_low     cycles, dispatch-resource stalls of event 0xae, unit-mask bits 0 to 3
//   ae_high    cycles, the same, bits 4 to 7
//   af_low     cycles, dispatch-resource stalls of event 0xaf, unit-mask bits 0 to 3
//   af_high    cycles, the same, bits 4 to 7
// Encodings, as every cell records them (counter_events):
//   cycles        PERF_COUNT_HW_CPU_CYCLES
//   l1d_misses    PERF_COUNT_HW_CACHE_L1D, read, miss
//   l2_misses     AMD family 19h raw event 0x64, unit mask 0x08: L2 cache request status,
//                 data cache request miss in L2 (l2_cache_req_stat.ls_rd_blk_c)
//   dtlb_misses   AMD family 19h raw event 0x45, unit mask 0xff: L1 data TLB misses
//                 (l1_dtlb_misses)
//   stall_ae_bK   AMD family 19h raw event 0xae, unit mask 1 << K: dispatch-resource stall
//                 cycles for the resource of bit K
//   stall_af_bK   AMD family 19h raw event 0xaf, unit mask 1 << K: the same for event 0xaf
// Each unit-mask bit is counted on its own and reported on its own: two bits can count the
// same cycle, so the bits of an event, or the two events, are never added. The kernel maps
// no generic backend-stall event on Zen 3 (stalled-cycles-backend is not supported), so these
// stand for it. Their behaviour on a pointer chase against a dependent multiply chain is in
// the lab journal (2026-09-27, the validation of the dispatch-resource stall counters), with
// its source in lab/evidence/2026-09-27-L-dispatch-stall-validation/. On any CPU other than
// AMD family 19h the raw events are not opened and their fields are null: another encoding
// is never substituted.
#pragma once

#include <cstdint>
#include <string>

namespace rb::hwc {

enum class Set { Memory, AeLow, AeHigh, AfLow, AfHigh };
inline constexpr Set kSets[] = {Set::Memory, Set::AeLow, Set::AeHigh, Set::AfLow, Set::AfHigh};

struct Totals {
    bool ok = false;              // the group was scheduled for the whole count
    bool raw = false;             // the AMD family 19h raw events were opened
    double running_fraction = 0;  // time running / time enabled
    std::uint64_t cycles = 0;
    std::uint64_t v[4] = {};      // the set's events after cycles, in the order above
    std::string error;            // why ok or raw is false
};

// The encodings above, as recorded in every cell.
const char* events();

// The names of a set's events after cycles, as the cell's fields are named ("" past the end).
const char* field(Set set, int i);

// Counts one set's user-space events of the calling thread while body() runs.
class Group {
public:
    explicit Group(Set set);
    ~Group();
    Group(const Group&) = delete;
    Group& operator=(const Group&) = delete;

    template <class F>
    Totals count(F&& body) {
        start();
        body();
        return stop();
    }

private:
    void start();
    Totals stop();

    int fd_[5];
    int n_ = 0;       // events opened, the leader included
    int want_ = 0;    // events the set has
    bool raw_ = false;
    std::string error_;
};

}  // namespace rb::hwc
