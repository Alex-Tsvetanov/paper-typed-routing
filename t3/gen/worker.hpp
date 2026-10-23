// The logic of one p2gen thread, the same code on both systems (the network is net.hpp). The
// thread owns its share of the connections and runs them in a closed loop at depth 1: connect,
// send one request, read its answer, send the next. It counts what happens (stats.hpp) and
// nothing else crosses threads except the Shared state below.
//
// How a connection ends, and how it comes back:
//   - An answer that is 200 with the 13-byte body completes the request. Any other answer that
//     frames counts as a status or a body error; the connection stays.
//   - Bytes that cannot be framed count as a framing error: the connection is closed.
//   - Bytes after an answer, or with no request in flight, count as unsolicited: it is closed.
//   - A request with no progress for --timeout-ms counts as a timeout: it is closed.
//   - A reset, or a close by the server, with a request in flight counts that request as lost.
//   - A refused connection attempt counts as a connect error.
//   - Connection: close in an answer: the connection is closed once the answer is counted.
// A closed connection is made again by the housekeeping pass (every 2 ms), never from inside an
// event, after a delay that is t1gen's: 10 ms after a connect error, 1 ms after a reset or an
// unframeable answer, none otherwise. Reconnections count.
#pragma once

#include <atomic>
#include <cstdint>
#include <memory>

#include "framing.hpp"
#include "net.hpp"
#include "options.hpp"
#include "requests.hpp"
#include "stats.hpp"

namespace p2gen {

enum Phase : int { kWarmup = 0, kMeasure = 1, kStop = 2 };

// What the threads share. Everything but the atomics is read only.
struct Shared {
    Shared(const Options& o, const Requests& r, const sockaddr_in& a)
        : opts(o), reqs(r), addr(a), counting(o.counting()), phase(o.counting() ? kMeasure : kWarmup) {}

    const Options& opts;
    const Requests& reqs;
    sockaddr_in addr;
    bool counting;
    std::atomic<int> phase;                    // set by main
    std::atomic<std::uint64_t> claimed{0};     // count mode: requests taken from the --count budget
    std::atomic<bool> abort{false};            // count mode: a thread could not run, so all stop
};

class Worker final : private NetHandler {
public:
    // Serves connections [first, first + n) of the run's opts.connections.
    Worker(int id, int cpu, int first, int n, Shared& shared);
    ~Worker();
    Worker(const Worker&) = delete;
    Worker& operator=(const Worker&) = delete;

    // The thread body.
    void run();

    const Stats& stats() const noexcept { return stats_; }

private:
    enum class State : std::uint8_t { Closed, Connecting, Open, Closing };
    enum class Outcome : std::uint8_t { Completed, Status, Body, Framing, Lost, Timeout };

    struct Conn : NetConn {
        State state = State::Closed;
        bool ever_open = false;
        bool inflight = false;
        bool done = false;         // count mode: the budget is spent, nothing more to send
        bool close_after = false;  // the answer said Connection: close
        std::size_t next = 0;      // the target of the next request
        std::uint64_t sent_at = 0;
        std::uint64_t last_progress = 0;
        std::uint64_t connect_start = 0;
        std::uint64_t retry_at = 0;
        std::uint64_t drop_delay_ns = 0;  // the delay after a close the worker asked for
        Framer framer;
    };

    // NetHandler
    bool begin_batch() override;
    void connected(NetConn& nc) override;
    void data(NetConn& nc, const char* p, std::size_t n) override;
    void closed(NetConn& nc, Cause why) override;

    void fail(const char* why);
    void start(Conn& c, std::uint64_t now);
    void issue(Conn& c, std::uint64_t now);
    void resolve(Conn& c, Outcome o);
    void drop(Conn& c, std::uint64_t delay_ns);
    void housekeeping(std::uint64_t now);
    void shutdown();
    bool finished() const;

    Counters& counters() noexcept { return stats_.phase[phase_index_]; }

    int id_;
    int cpu_;
    Shared& sh_;
    Net net_;
    int nconns_;
    std::unique_ptr<Conn[]> conns_;
    Stats stats_;
    int phase_index_;       // 0 before the window, 1 in it
    std::uint64_t timeout_ns_;
    std::size_t inflight_ = 0;
    bool stop_ = false;
    bool leak_ = false;     // operations outlived the drain: the connections must not be freed
};

}  // namespace p2gen
