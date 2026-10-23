// The one JSON line p2gen ends with, and the rule for its exit code. Pure code, so the tests can
// check, among other things, that count mode's line holds no time.
//
// Timed mode:
//   measure and warmup  the counters of the window and of the warm-up (below)
//   latency_ns          send-to-last-byte of the answers completed in the window
//   measure_wall_ns     the window's wall time, t1 - t0 of the steady clock
// Counters:
//   completed           answers that are 200 with the 13-byte body "Hello, World!"
//   errors.status       answers whose status is not 200
//   errors.body         200 answers whose body is not the 13 bytes
//   errors.framing      bytes that could not be read as an answer
//   errors.lost         requests in flight when the connection was reset or closed by the server
//   errors.unsolicited  bytes with no request in flight, or after an answer
//   timeouts            requests with no progress for --timeout-ms
//   errors_total        status + body + framing + lost + unsolicited + timeouts
//   connect_errors      connection attempts that were refused or failed
//   resets, peer_closes open connections that failed, or that the server closed
//   reconnects          attempts to connect again after a connection had once been open, each
//                       attempt counted, a refused one too: what t1gen's reconnects counts
//   reconnected         of those attempts, the connections that came up
// The runner requires peer_closes and reconnects to be 0 in the window; both are in measure.
// No rate is in the line: it is completed over measure_wall_ns, for the reader to compute.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

#include "histogram.hpp"
#include "options.hpp"
#include "stats.hpp"

namespace p2gen {

// The merge of every thread's Stats.
struct Totals {
    Counters warmup;
    Counters measure;
    Histogram latency;
    bool thread_failed = false;

    void fold(const Stats& s) {
        warmup.add(s.phase[0]);
        measure.add(s.phase[1]);
        latency.merge(s.latency);
        thread_failed = thread_failed || s.failed;
    }
};

std::string render_timed(const Options& o, std::string_view commit, std::size_t targets, std::size_t request_bytes,
                         std::uint64_t t0_ns, std::uint64_t t1_ns, const Totals& t);

// Counts and non-time configuration only.
std::string render_count(const Options& o, std::string_view commit, const Totals& t);

// Count mode succeeds only if every one of the N requests completed and nothing else went wrong:
// completed == N, every request has exactly one outcome, no error of any kind, no failed thread.
bool count_ok(const Options& o, const Totals& t) noexcept;

// A timed run fails its own checks only when a thread could not run.
bool timed_ok(const Totals& t) noexcept;

}  // namespace p2gen
