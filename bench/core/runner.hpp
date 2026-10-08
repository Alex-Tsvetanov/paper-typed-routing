// The measurement of one cell, as a template over the arm type. Included only by arm
// translation units; RB_ARM(Type) instantiates it and registers the arm.
//
// For one table and one ring the cell reports
//   build     wall time of all add() calls plus finalize(), repeated on fresh instances;
//             heap allocations made, the bytes they allocated, and heap bytes still held after
//             finalize(); and, for an arm that reports it (table_layout()), where its table lies
//   verify    the queries of the ring through lookup(), id and captured values compared
//             with the ring's expectation (the agreement test); every query unless an arm
//             is so slow that the pass exceeds verify_budget_s (verified_all says which)
//   allocs    heap allocations and bytes per lookup over one pass (malloc is counted only
//             in this pass and in the build, never in a timed loop: core/alloc_count.hpp)
//   lookup    nanobench epochs of whole passes: ns, instructions, branches, branch misses
//             and cycles per lookup (perf_event_open, user space only)
//   memory    L1d, L2 and L1 DTLB misses, and dispatch-resource stall cycles per unit-mask
//             bit of events 0xAE and 0xAF, per lookup, over whole passes after the epochs
//             (core/cache_counters.hpp)
//   latency   per-lookup time-stamp-counter samples, minus the empty-interval cost; for an
//             arm behind a foreign-function boundary they include one call across it
//             (latency_includes_ffi), so they are not comparable with the others'
// A slow arm's passes are cut to a prefix of the ring (lookups_per_pass says how long).
//
// Three optional hooks serve an arm behind a foreign-function boundary whose call costs as
// much as a lookup (Go's cgo):
//   std::uint64_t pass(const Ring&, std::size_t n)  runs n lookups inside the arm; the
//                                                    throughput passes use it (loop "arm")
//   static std::uint64_t own_allocs()               allocations the arm's runtime counts
//                                                    itself (Go's heap is not malloc's)
//   static void ffi_nop()                           an empty call across the boundary; its
//                                                    cost is reported as ffi_call_ns
//   static std::int64_t own_live_bytes()            bytes live on the arm runtime's own heap
//                                                    (Go's, after a collection), added to the
//                                                    table's bytes
//
// The null arm (`static constexpr bool null_arm = true`) has no router: its lookup is one
// out-of-line call that returns without matching. It skips the agreement test, and its
// instructions per lookup are the harness loop's, which summaries subtract from the arms
// whose throughput loop is the harness's.
//
// 405: an arm whose lookup does not tell 404 from 405 itself (no `static constexpr bool
// native_405 = true`) gets the harness's rule, the one Crow's router and httprouter apply:
// on a miss, the same path is looked up under every other method that has routes, and any
// hit makes the answer kMethodNotAllowed. Every lookup the harness makes goes through it,
// timed or not; on the all-hit rings of the grid it never runs.
//
// Every timed loop folds the route id and every captured value (its length and first byte)
// into a sink the compiler cannot drop, so no arm's capture work can be optimised away.
#pragma once

#include <nanobench.h>

#include <algorithm>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

#include "core/alloc_count.hpp"
#include "core/arm.hpp"
#include "core/cache_counters.hpp"
#include "core/json.hpp"
#include "core/tsc.hpp"

namespace rb {

template <class A>
concept HasPass = requires(A& a, const Ring& r, std::size_t n) {
    { a.pass(r, n) } -> std::same_as<std::uint64_t>;
};
template <class A>
concept HasOwnAllocs = requires {
    { A::own_allocs() } -> std::same_as<std::uint64_t>;
};
template <class A>
concept HasFfiNop = requires { A::ffi_nop(); };
template <class A>
concept HasOwnLive = requires {
    { A::own_live_bytes() } -> std::same_as<std::int64_t>;
};
template <class A>
concept HasNative405 = requires {
    requires A::native_405;
};
template <class A>
concept IsNull = requires {
    requires A::null_arm;
};
// An arm whose runtime has processors and collections of its own (the Go arms): GOMAXPROCS and
// the number of completed collections, read before and after the timed epochs.
template <class A>
concept HasRuntimeStats = requires {
    { A::runtime_procs() } -> std::same_as<int>;
    { A::runtime_gc_cycles() } -> std::same_as<std::uint64_t>;
};
template <class A>
concept HasNullPass = requires(A& a, const Ring& r, std::size_t n) {
    { a.null_pass(r, n) } -> std::same_as<std::uint64_t>;
};
// An arm that reports where its table lies (a JSON object, for example the page offsets of its
// arrays), recorded with the build.
template <class A>
concept HasLayout = requires(const A& a) {
    { a.table_layout() } -> std::same_as<std::string>;
};

namespace detail {

inline bool rest_capture(const Table& t, RouteId id, std::size_t i) {
    if (id == kNoRoute || id >= t.routes.size()) {
        return false;
    }
    const auto& segs = t.routes[id].segs;
    std::size_t params = 0;
    for (const auto& s : segs) {
        params += s.kind != Seg::Literal;
    }
    return !segs.empty() && segs.back().kind == Seg::Rest && i + 1 == params;
}

// A catch-all value may come back with its leading '/' (httprouter keeps it); both forms
// count as the same value.
inline bool same_value(std::string_view got, std::string_view want, bool rest) {
    if (rest && got.size() == want.size() + 1 && got.front() == '/') {
        got.remove_prefix(1);
    }
    return got == want;
}

// What a timed loop keeps of one lookup: the id and every captured value.
inline std::uint64_t fold(RouteId id, const Captures& c) {
    std::uint64_t s = id;
    for (std::uint8_t i = 0; i < c.n; ++i) {
        s += c.v[i].size() + (c.v[i].empty() ? 0u : static_cast<unsigned char>(c.v[i].front()));
    }
    return s;
}

inline std::uint16_t methods_of(const std::vector<Route>& routes) {
    std::uint16_t m = 0;
    for (const Route& r : routes) {
        m = static_cast<std::uint16_t>(m | (1u << static_cast<unsigned>(r.method)));
    }
    return m;
}

inline double percentile(std::vector<double>& v, double q) {
    if (v.empty()) {
        return 0.0;
    }
    const auto k = static_cast<std::size_t>(std::min<double>(static_cast<double>(v.size() - 1),
                                                             std::floor(q * static_cast<double>(v.size()))));
    std::nth_element(v.begin(), v.begin() + static_cast<std::ptrdiff_t>(k), v.end());
    return v[k];
}

}  // namespace detail

template <Arm A>
class ArmRunner final : public Runner {
public:
    ArmInfo describe() const override { return A::info(); }

    void build(const std::vector<Route>& routes) override {
        arm_.reset();
        auto a = std::make_unique<A>();
        for (RouteId id = 0; id < routes.size(); ++id) {
            a->add(routes[id], id);
        }
        a->finalize();
        arm_ = std::move(a);
        methods_ = detail::methods_of(routes);
    }

    RouteId lookup(Method m, const std::string& path, std::vector<std::string>& caps) override {
        Captures c;
        const RouteId id = full(m, path, c);
        caps.assign(c.v.begin(), c.v.begin() + c.n);
        return id;
    }

    std::string measure(const Table& t, const Ring& r, const MeasureOptions& o) override {
        const ArmInfo info = A::info();
        Json j;
        j.str("arm", info.name).str("version", info.version).str("captures", info.captures);
        j.str("shape", shape_name(t.spec.shape)).num("m", t.spec.m).num("table_seed", t.spec.seed);
        j.num("methods", t.spec.methods).str("table_digest", t.digest);
        j.num("ring_size", r.queries.size()).num("ring_seed", r.spec.seed);
        j.num("miss_permille", r.spec.miss_permille).str("ring_digest", r.digest);
        j.str("vocabulary", t.spec.long_words ? "long" : "default").num("zipf", r.spec.zipf);
        j.boolean("decoys", r.spec.decoys);
        {
            const RingWalk w = ring_walk(t, r);  // a property of table and ring, not of the arm
            j.num("ring_exact", w.exact).num("ring_backtracking", w.backtracking).num("ring_pops", w.pops);
        }
        j.str("alloc_mechanism", alloc::mechanism());

        // The ring the timed loops read: the methods, and the paths copied one after another
        // before any arm is built, so that their buffers are allocated back to back and no
        // arm's allocations fall between them. A Query also holds its expected values, so
        // walking the queries themselves would pull several times the bytes a server reads per
        // request through the caches, which the arms whose passes run in their own runtime (the
        // Go arms, over the paths they loaded) do not pay. The cell records where the copy lies.
        make_ring_copy(r);
        {
            const RingSpan span = ring_span();
            j.str("ring_layout", o.ring_from_queries ? "queries" : "copy");
            j.num("ring_copy_bytes", span.bytes).num("ring_copy_span_bytes", span.span).num("ring_copy_pages", span.pages);
            j.boolean("ring_copy_contiguous", copy_->contiguous);
        }
        from_queries_ = o.ring_from_queries;

        // Build.
        methods_ = detail::methods_of(t.routes);
        std::vector<double> build_s;
        std::uint64_t build_allocs = 0;
        std::uint64_t build_alloc_bytes = 0;
        std::int64_t table_bytes = 0;
        std::int64_t own_bytes = 0;
        for (int rep = 0; rep < o.build_reps; ++rep) {
            arm_.reset();
            std::uint64_t own0 = 0;
            std::int64_t live0 = 0;
            if constexpr (HasOwnAllocs<A>) {
                own0 = A::own_allocs();
            }
            if constexpr (HasOwnLive<A>) {
                live0 = A::own_live_bytes();
            }
            std::unique_ptr<A> a;
            alloc::Snapshot s0;
            alloc::Snapshot s1;
            std::chrono::steady_clock::time_point t0;
            std::chrono::steady_clock::time_point t1;
            try {
                const alloc::Window counting;
                s0 = alloc::now();
                t0 = std::chrono::steady_clock::now();
                a = std::make_unique<A>();
                for (RouteId id = 0; id < t.routes.size(); ++id) {
                    a->add(t.routes[id], id);
                }
                a->finalize();
                t1 = std::chrono::steady_clock::now();
                s1 = alloc::now();
            } catch (const Refused& e) {
                j.str("status", "refused").str("reason", e.what());
                return j.done();
            }
            build_s.push_back(std::chrono::duration<double>(t1 - t0).count());
            build_allocs = s1.calls - s0.calls;
            build_alloc_bytes = s1.bytes - s0.bytes;
            table_bytes = s1.live - s0.live;
            if constexpr (HasOwnAllocs<A>) {
                build_allocs += A::own_allocs() - own0;
            }
            if constexpr (HasOwnLive<A>) {
                own_bytes = A::own_live_bytes() - live0;
                table_bytes += own_bytes;
            }
            arm_ = std::move(a);
            if (build_s.back() > o.build_budget_s) {
                break;
            }
        }
        std::vector<double> sorted = build_s;
        j.nums("build_s", build_s).num("build_s_median", detail::percentile(sorted, 0.5));
        j.num("build_allocs", build_allocs).num("build_alloc_bytes", build_alloc_bytes).num("table_bytes", table_bytes);
        if constexpr (HasLayout<A>) {
            j.raw("table_layout", arm_->table_layout());
        }
        if constexpr (HasOwnLive<A>) {
            j.num("own_table_bytes", own_bytes);
        }

        // Agreement with the ring's expectation, on every query (the null arm has no router).
        const bool check = !IsNull<A>;
        j.boolean("null_arm", !check);
        std::uint64_t id_bad = 0;
        std::uint64_t id_bad_404 = 0;  // of those, answered "no route" (semantics.json's kind "404")
        std::uint64_t cap_bad = 0;
        std::vector<std::string> errors;
        const auto p0 = std::chrono::steady_clock::now();
        std::size_t verified = 0;
        for (const Query& q : r.queries) {
            if (verified >= 64 &&
                std::chrono::duration<double>(std::chrono::steady_clock::now() - p0).count() > o.verify_budget_s) {
                break;
            }
            ++verified;
            Captures c;
            const RouteId id = full(q.method, q.path, c);
            bool ok = !check || id == q.expect;
            if (!ok) {
                ++id_bad;
                id_bad_404 += id == kNoRoute ? 1u : 0u;
            } else if (check) {
                bool caps_ok = c.n == q.caps.size();
                for (std::size_t i = 0; caps_ok && i < c.n; ++i) {
                    caps_ok = detail::same_value(c.v[i], q.caps[i], detail::rest_capture(t, id, i));
                }
                if (!caps_ok) {
                    ++cap_bad;
                    ok = false;
                }
            }
            if (!ok && errors.size() < 3) {
                std::string e = q.path + " -> " + id_text(id) + " (want " + id_text(q.expect) + "), captures [";
                for (std::size_t i = 0; i < c.n; ++i) {
                    e += (i ? "," : "") + std::string(c.v[i]);
                }
                errors.push_back(e + "]");
            }
        }
        const double pass_s = std::chrono::duration<double>(std::chrono::steady_clock::now() - p0).count() *
                              static_cast<double>(r.queries.size()) / static_cast<double>(verified);
        const bool agrees = id_bad == 0 && cap_bad == 0;
        j.num("verified", verified).boolean("verified_all", verified == r.queries.size());
        j.num("id_mismatches", id_bad).num("id_mismatches_404", id_bad_404).num("capture_mismatches", cap_bad);
        j.strs("mismatch_examples", errors).boolean("agrees", agrees);
        // An arm that answers some queries differently is still measured, so that a shape on
        // which its path semantics differ (bench/semantics.json) can report its timing beside
        // the number of answers that differ; its cell is "disagrees" and never counts in H1.
        j.num("answers_differ", id_bad + cap_bad);

        // Passes over a slow arm are cut to a prefix of the (randomly ordered) ring.
        std::size_t n = r.queries.size();
        if (pass_s > o.pass_budget_s) {
            n = std::max<std::size_t>(16, static_cast<std::size_t>(static_cast<double>(n) * o.pass_budget_s / pass_s));
        }
        j.num("lookups_per_pass", n);

        // Allocations per lookup, over one pass.
        {
            std::uint64_t own = 0;
            if constexpr (HasOwnAllocs<A>) {
                own = A::own_allocs();
            }
            alloc::Snapshot s0;
            alloc::Snapshot s1;
            std::uint64_t sink = 0;
            {
                const alloc::Window counting;
                s0 = alloc::now();
                sink = harness_pass(r, n);
                s1 = alloc::now();
            }
            ankerl::nanobench::doNotOptimizeAway(sink);
            if constexpr (HasOwnAllocs<A>) {
                own = A::own_allocs() - own;
                j.num("own_allocs_per_lookup", static_cast<double>(own) / static_cast<double>(n));
            }
            j.num("allocs_per_lookup", static_cast<double>(s1.calls - s0.calls + own) / static_cast<double>(n));
            j.num("alloc_bytes_per_lookup", static_cast<double>(s1.bytes - s0.bytes) / static_cast<double>(n));
        }

        // Throughput passes with hardware counters.
        std::uint64_t gc_before = 0;
        if constexpr (HasRuntimeStats<A>) {
            gc_before = A::runtime_gc_cycles();
        }
        ankerl::nanobench::Bench bench;
        bench.output(nullptr)
            .epochs(static_cast<std::size_t>(o.epochs))
            .warmup(1)
            .minEpochIterations(1)
            .minEpochTime(std::chrono::milliseconds(5))
            .batch(static_cast<double>(n))
            .performanceCounters(true)
            .run(info.name, [&] { ankerl::nanobench::doNotOptimizeAway(one_pass(r, n)); });
        if constexpr (HasRuntimeStats<A>) {
            j.num("go_maxprocs", A::runtime_procs());
            j.num("go_gc_cycles_in_epochs", A::runtime_gc_cycles() - gc_before);
        }
        j.str("throughput_loop", HasPass<A> ? "arm" : "harness");
        // What H2 subtracts from this arm's instructions (the loop and the sink around its
        // lookups): for the harness's loop, the C++ null arm of the same 405 rule in the same
        // cell ("null" for an arm with its own 405; "null-no405", which gets the harness's 405
        // test as such an arm does, for an arm without); the arm's own null pass for a loop in
        // another runtime ("own", measured below); nothing for a null arm.
        if constexpr (IsNull<A>) {
            j.str("loop_null", "");
        } else if constexpr (HasNullPass<A>) {
            j.str("loop_null", "own");
        } else if constexpr (HasPass<A>) {
            j.str("loop_null", "");
        } else if constexpr (HasNative405<A>) {
            j.str("loop_null", "null");
        } else {
            j.str("loop_null", "null-no405");
        }
        using M = ankerl::nanobench::Result::Measure;
        const auto& res = bench.results().back();
        const double per = 1.0 / static_cast<double>(n);
        std::vector<double> epoch_ns;
        for (std::size_t e = 0; e < res.size(); ++e) {
            epoch_ns.push_back(res.get(e, M::elapsed) * per * 1e9);
        }
        j.nums("epoch_ns", epoch_ns).num("ns_median", res.median(M::elapsed) * per * 1e9);
        j.num("ns_mdape", res.medianAbsolutePercentError(M::elapsed));
        j.num("epoch_iterations", res.median(M::iterations));
        const auto counter = [&](const char* key, M m) {
            if (res.has(m)) {
                j.num(key, res.median(m) * per);
            } else {
                j.null(key);
            }
        };
        counter("instructions", M::instructions);
        if (res.has(M::instructions)) {
            j.num("instructions_mdape", res.medianAbsolutePercentError(M::instructions));
        }
        counter("branches", M::branchinstructions);
        counter("branch_misses", M::branchmisses);
        counter("cycles", M::cpucycles);

        // The arm's own null pass (the Go arms): the same loop over the same loaded data with no
        // router in it, measured as the passes above are.
        if constexpr (HasNullPass<A>) {
            ankerl::nanobench::Bench null_bench;
            null_bench.output(nullptr)
                .epochs(static_cast<std::size_t>(o.epochs))
                .warmup(1)
                .minEpochIterations(1)
                .minEpochTime(std::chrono::milliseconds(5))
                .batch(static_cast<double>(n))
                .performanceCounters(true)
                .run("null pass", [&] { ankerl::nanobench::doNotOptimizeAway(arm_->A::null_pass(r, n)); });
            const auto& nres = null_bench.results().back();
            j.num("null_ns", nres.median(M::elapsed) * per * 1e9);
            if (nres.has(M::instructions)) {
                j.num("null_instructions", nres.median(M::instructions) * per);
            } else {
                j.null("null_instructions");
            }
        }

        // Memory-side counters over whole passes, one group after another
        // (core/cache_counters.hpp), each over at least three passes and 50 ms.
        {
            j.str("counter_events", hwc::events());
            std::string notes;
            std::uint64_t sink = 0;
            for (const hwc::Set set : hwc::kSets) {
                hwc::Group group(set);
                std::uint64_t passes = 0;
                const hwc::Totals tot = group.count([&] {
                    const auto t0 = std::chrono::steady_clock::now();
                    do {
                        sink += one_pass(r, n);
                        ++passes;
                    } while (passes < 3 ||
                             std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count() < 0.05);
                });
                const double lookups = static_cast<double>(passes * n);
                const auto per = [&](const char* key, bool have, std::uint64_t v) {
                    if (have) {
                        j.num(key, static_cast<double>(v) / lookups);
                    } else {
                        j.null(key);
                    }
                };
                const bool memory = set == hwc::Set::Memory;
                if (memory) {
                    per("memory_cycles", tot.ok, tot.cycles);
                }
                for (int i = 0; *hwc::field(set, i) != '\0'; ++i) {
                    // l1d_misses is a generic event; every other one is an AMD raw event.
                    per(hwc::field(set, i), tot.ok && (tot.raw || (memory && i == 0)), tot.v[i]);
                }
                if (!tot.error.empty()) {
                    notes += (notes.empty() ? "" : "; ") + std::string(hwc::field(set, 0)) + ": " + tot.error;
                }
            }
            ankerl::nanobench::doNotOptimizeAway(sink);
            if (!notes.empty()) {
                j.str("counter_note", notes);
            }
        }

        // Per-lookup latency samples.
        const double tpn = ticks_per_ns();
        const std::uint64_t overhead = tsc::overhead_ticks();
        const double ns_each = std::max(1.0, res.median(M::elapsed) * per * 1e9);
        const auto budget_samples = static_cast<std::uint64_t>(o.latency_budget_s * 1e9 / ns_each);
        const std::uint64_t want = std::max<std::uint64_t>(n, std::min(o.latency_samples, budget_samples));
        std::vector<double> lat;
        lat.reserve(want);
        std::uint64_t sink = 0;
        for (std::uint64_t k = 0; k < want; ++k) {
            const std::size_t q = static_cast<std::size_t>(k % n);
            const Method qm = from_queries_ ? r.queries[q].method : copy_->methods[q];
            const std::string& qp = from_queries_ ? r.queries[q].path : copy_->paths[q];
            Captures c;
            const std::uint64_t a = tsc::start();
            const RouteId id = full(qm, qp, c);
            const std::uint64_t b = tsc::stop();
            sink += detail::fold(id, c);
            const std::uint64_t d = b - a;
            lat.push_back(static_cast<double>(d > overhead ? d - overhead : 0) / tpn);
        }
        ankerl::nanobench::doNotOptimizeAway(sink);
        j.boolean("latency_includes_ffi", HasFfiNop<A>);
        j.num("latency_samples", lat.size()).num("tsc_ticks_per_ns", tpn).num("tsc_overhead_ticks", overhead);
        j.num("lat_p50_ns", detail::percentile(lat, 0.50)).num("lat_p90_ns", detail::percentile(lat, 0.90));
        j.num("lat_p99_ns", detail::percentile(lat, 0.99)).num("lat_p999_ns", detail::percentile(lat, 0.999));
        j.num("lat_max_ns", *std::max_element(lat.begin(), lat.end()));
        if constexpr (HasFfiNop<A>) {
            constexpr int kCalls = 1 << 16;
            std::vector<double> per_call;
            for (int rep = 0; rep < 11; ++rep) {
                const auto t0 = std::chrono::steady_clock::now();
                for (int i = 0; i < kCalls; ++i) {
                    A::ffi_nop();
                }
                per_call.push_back(std::chrono::duration<double, std::nano>(std::chrono::steady_clock::now() - t0).count() /
                                   kCalls);
            }
            j.num("ffi_call_ns", detail::percentile(per_call, 0.5));
        }
        j.str("status", agrees ? "ok" : "disagrees");
        return j.done();
    }

private:
    static std::string id_text(RouteId id) {
        return id == kNoRoute ? "404" : (id == kMethodNotAllowed ? "405" : std::to_string(id));
    }

    // One pass of n lookups, as the timed epochs run it: inside the arm when it has pass(),
    // else through full() here. Returns the sink.
    std::uint64_t one_pass(const Ring& r, std::size_t n) {
        if constexpr (HasPass<A>) {
            return arm_->A::pass(r, n);
        } else {
            return harness_pass(r, n);
        }
    }

    // n lookups through full() over the ring's compact copy, or over its queries.
    std::uint64_t harness_pass(const Ring& r, std::size_t n) {
        std::uint64_t sink = 0;
        if (from_queries_) {
            for (std::size_t i = 0; i < n; ++i) {
                Captures c;
                const RouteId id = full(r.queries[i].method, r.queries[i].path, c);
                sink += detail::fold(id, c);
            }
        } else {
            for (std::size_t i = 0; i < n; ++i) {
                Captures c;
                const RouteId id = full(copy_->methods[i], copy_->paths[i], c);
                sink += detail::fold(id, c);
            }
        }
        return sink;
    }

    // The copy lives in one contiguous block (alloc::Arena) where malloc is interposed, and is
    // never freed: its vectors are held by a heap object that is kept for the process's life.
    void make_ring_copy(const Ring& r) {
        std::size_t bytes = 64 + r.queries.size() * (sizeof(Method) + sizeof(std::string) + 32);
        for (const Query& q : r.queries) {
            bytes += (q.path.size() + 1 + 15) / 16 * 16;
        }
        auto* copy = new RingCopy;  // never deleted (see kept_copies)
        kept_copies().push_back(copy);
        {
            const alloc::Arena arena(bytes);
            copy->methods.reserve(r.queries.size());
            copy->paths.reserve(r.queries.size());
            for (const Query& q : r.queries) {
                copy->methods.push_back(q.method);
            }
            for (const Query& q : r.queries) {
                copy->paths.push_back(q.path);
            }
            copy->contiguous = alloc::arena_used() && arena.whole();
        }
        copy_ = copy;
    }

    struct RingCopy {
        std::vector<Method> methods;
        std::vector<std::string> paths;
        bool contiguous = false;
    };

    // Every copy made in this process, reachable for its whole life, so its arena block is
    // never freed and no leak check reports it.
    static std::vector<RingCopy*>& kept_copies() {
        static std::vector<RingCopy*>* kept = new std::vector<RingCopy*>;
        return *kept;
    }

    struct RingSpan {
        std::uint64_t bytes = 0;  // path bytes
        std::uint64_t span = 0;   // from the lowest to the highest byte of the copy
        std::uint64_t pages = 0;  // distinct 4 KiB pages it touches
    };

    // Where the compact copy lies: its path bytes, its string objects and its methods.
    RingSpan ring_span() const {
        RingSpan s;
        std::uintptr_t lo = UINTPTR_MAX;
        std::uintptr_t hi = 0;
        std::vector<std::uintptr_t> pages;
        const auto cover = [&](const void* p, std::size_t len) {
            if (len == 0) {
                return;
            }
            const auto a = reinterpret_cast<std::uintptr_t>(p);
            lo = std::min(lo, a);
            hi = std::max(hi, a + len);
            for (std::uintptr_t pg = a >> 12; pg <= (a + len - 1) >> 12; ++pg) {
                pages.push_back(pg);
            }
        };
        cover(copy_->methods.data(), copy_->methods.size() * sizeof(Method));
        cover(copy_->paths.data(), copy_->paths.size() * sizeof(std::string));
        for (const std::string& p : copy_->paths) {
            s.bytes += p.size();
            cover(p.data(), p.size());
        }
        std::sort(pages.begin(), pages.end());
        s.pages = static_cast<std::uint64_t>(std::unique(pages.begin(), pages.end()) - pages.begin());
        s.span = hi > lo ? hi - lo : 0;
        return s;
    }

    // One lookup under the harness's rules (the 405 rule above).
    RouteId full(Method m, const std::string& path, Captures& c) {
        const RouteId id = arm_->A::lookup(m, path, c);
        if constexpr (!HasNative405<A>) {
            if (id == kNoRoute) {
                unsigned others = methods_ & ~(1u << static_cast<unsigned>(m));
                while (others != 0) {
                    const auto other = static_cast<Method>(std::countr_zero(others));
                    others &= others - 1;
                    Captures scratch;
                    const RouteId o = arm_->A::lookup(other, path, scratch);
                    if (o != kNoRoute && o != kMethodNotAllowed) {
                        c.n = 0;
                        return kMethodNotAllowed;
                    }
                }
            }
        }
        return id;
    }

    static double ticks_per_ns() {
        static const double v = tsc::ticks_per_ns();
        return v;
    }

    std::unique_ptr<A> arm_;
    const RingCopy* copy_ = nullptr;  // the timed loops' ring (see measure)
    bool from_queries_ = false;
    std::uint16_t methods_ = 0;
};

}  // namespace rb

#define RB_ARM(Type)                                                                          \
    namespace {                                                                              \
    [[maybe_unused]] const bool rb_registered_arm = ::rb::register_arm(                     \
        Type::info().name, []() -> std::unique_ptr<::rb::Runner> {                          \
            return std::make_unique<::rb::ArmRunner<Type>>();                                \
        });                                                                                  \
    }
