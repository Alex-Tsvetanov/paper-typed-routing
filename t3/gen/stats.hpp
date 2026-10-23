// What a worker thread counts. Each thread owns its Stats; main merges them after the joins, so no
// counter is shared while the run goes on.
#pragma once

#include <cstdint>

#include "histogram.hpp"

namespace p2gen {

struct Counters {
    std::uint64_t completed = 0;       // 200 with the 13-byte body
    std::uint64_t status = 0;          // an answer whose status is not 200
    std::uint64_t body = 0;            // a 200 whose body is not "Hello, World!"
    std::uint64_t framing = 0;         // bytes that cannot be framed as an answer
    std::uint64_t lost = 0;            // requests in flight when the connection was reset or closed
    std::uint64_t timeouts = 0;        // requests with no progress for --timeout-ms
    std::uint64_t unsolicited = 0;     // bytes with no request in flight, or after the answer
    std::uint64_t connect_errors = 0;  // connection attempts that were refused or failed
    std::uint64_t resets = 0;          // open connections that failed with a socket error
    std::uint64_t peer_closes = 0;     // open connections the server closed
    std::uint64_t reconnects = 0;      // connections made again after one was lost or closed

    // Requests that got an outcome, completed or not. In count mode this must equal --count.
    std::uint64_t resolved() const noexcept { return completed + status + body + framing + lost + timeouts; }

    // Everything that went wrong, timeouts included, as t1gen's errors_total does.
    std::uint64_t errors() const noexcept { return status + body + framing + lost + timeouts + unsolicited; }

    void add(const Counters& o) noexcept {
        completed += o.completed;
        status += o.status;
        body += o.body;
        framing += o.framing;
        lost += o.lost;
        timeouts += o.timeouts;
        unsolicited += o.unsolicited;
        connect_errors += o.connect_errors;
        resets += o.resets;
        peer_closes += o.peer_closes;
        reconnects += o.reconnects;
    }
};

// The counters of a thread: [0] before the window (the warm-up), [1] inside it. In count mode
// everything is in [1] and the histogram stays empty.
struct Stats {
    Counters phase[2];
    Histogram latency;
    bool failed = false;
};

}  // namespace p2gen
