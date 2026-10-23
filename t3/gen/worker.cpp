#include "worker.hpp"

#include <cstdio>

namespace p2gen {

namespace {

constexpr std::uint64_t kHousekeepingNs = 2'000'000;       // a housekeeping pass at most every 2 ms
constexpr int kWaitMs = 5;                                 // the longest one wait lasts
constexpr std::uint64_t kConnectErrorDelayNs = 10'000'000;  // before trying again after a refusal
constexpr std::uint64_t kResetDelayNs = 1'000'000;          // after a reset or an unframeable answer
constexpr int kDrainMs = 5000;                             // the longest the end waits for operations

}  // namespace

static_assert(alignof(Worker) == kCacheLine && sizeof(Worker) % kCacheLine == 0,
              "a Worker must fill whole cache lines");

Worker::Worker(int id, int cpu, int first, int n, Shared& shared)
    : id_(id),
      cpu_(cpu),
      sh_(shared),
      net_(*this, shared.addr),
      nconns_(n),
      conns_(new Conn[static_cast<std::size_t>(n)]),
      phase_index_(shared.counting ? 1 : 0),
      timeout_ns_(static_cast<std::uint64_t>(shared.opts.timeout_ms) * 1'000'000) {
    static_assert(alignof(Conn) == kCacheLine && sizeof(Conn) % kCacheLine == 0,
                  "a Conn must fill whole cache lines");
    // Connection i of C starts at target i * (number of targets) / C and walks them cyclically.
    const std::uint64_t targets = sh_.reqs.size();
    const std::uint64_t total = static_cast<std::uint64_t>(sh_.opts.connections);
    for (int j = 0; j < n; ++j) {
        conns_[static_cast<std::size_t>(j)].next =
            static_cast<std::size_t>(static_cast<std::uint64_t>(first + j) * targets / total);
    }
}

Worker::~Worker() {
    if (leak_) {
        [[maybe_unused]] Conn* left = conns_.release();  // an operation may still write into it
    }
}

void Worker::fail(const char* why) {
    std::fprintf(stderr, "p2gen: thread %d: %s\n", id_, why);
    stats_.failed = true;
    if (sh_.counting) {
        sh_.abort.store(true, std::memory_order_relaxed);
    }
}

void Worker::run() {
    if (cpu_ >= 0 && !pin_current_thread(cpu_)) {
        char why[64];
        std::snprintf(why, sizeof why, "cannot pin to cpu %d", cpu_);
        fail(why);
        return;
    }
    if (!net_.init()) {
        fail("cannot set up the network backend");
        return;
    }
    std::uint64_t now = clock_ns();
    for (int j = 0; j < nconns_; ++j) {
        start(conns_[static_cast<std::size_t>(j)], now);
    }
    std::uint64_t next_housekeeping = now + kHousekeepingNs;
    while (!stop_) {
        net_.poll(kWaitMs);
        if (stop_) {
            break;
        }
        if (!net_.ok()) {
            fail("waiting for network events failed");
            break;
        }
        now = clock_ns();
        if (now >= next_housekeeping) {
            housekeeping(now);
            next_housekeeping = now + kHousekeepingNs;
        }
        if (sh_.counting && finished()) {
            break;
        }
    }
    shutdown();
}

// Count mode ends for a thread when the budget is spent and none of its requests is in flight,
// or when another thread could not run.
bool Worker::finished() const {
    return sh_.abort.load(std::memory_order_relaxed) ||
           (sh_.claimed.load(std::memory_order_relaxed) >= sh_.opts.count && inflight_ == 0);
}

void Worker::shutdown() {
    for (int j = 0; j < nconns_; ++j) {
        net_.close(conns_[static_cast<std::size_t>(j)]);
    }
    if (!net_.drain(kDrainMs)) {
        leak_ = true;
    }
}

bool Worker::begin_batch() {
    const int p = sh_.phase.load(std::memory_order_acquire);
    if (p == kStop) {
        stop_ = true;
        return false;
    }
    // A batch belongs to the phase current when the thread picks it up, at both edges of the window
    // (as t1gen), so the window keeps its length and the count is not biased in steady state.
    phase_index_ = p == kMeasure ? 1 : 0;
    return true;
}

void Worker::start(Conn& c, std::uint64_t now) {
    if (c.ever_open) {
        ++counters().reconnects;  // as t1gen: every attempt after the first connection was open
    }
    c.state = State::Connecting;
    c.connect_start = now;
    c.close_after = false;
    c.framer.reset();
    net_.connect(c);
}

void Worker::connected(NetConn& nc) {
    Conn& c = static_cast<Conn&>(nc);
    const std::uint64_t now = clock_ns();
    c.state = State::Open;
    if (c.ever_open) {
        ++counters().reconnected;
    }
    c.ever_open = true;
    issue(c, now);
}

// Sends the connection's next request, if the run has one for it.
void Worker::issue(Conn& c, std::uint64_t now) {
    if (sh_.counting && sh_.claimed.fetch_add(1, std::memory_order_relaxed) >= sh_.opts.count) {
        c.done = true;  // the budget is spent: this connection has nothing more to send
        return;
    }
    const std::string_view request = sh_.reqs.get(c.next);
    c.next = c.next + 1 == sh_.reqs.size() ? 0 : c.next + 1;
    c.inflight = true;
    ++inflight_;
    c.last_progress = now;
    if (!sh_.counting) {
        c.sent_at = now;  // latency runs from the moment the request is queued
    }
    net_.send(c, request.data(), request.size());
}

void Worker::data(NetConn& nc, const char* p, std::size_t n) {
    Conn& c = static_cast<Conn&>(nc);
    const std::uint64_t now = clock_ns();
    c.last_progress = now;
    if (!c.inflight) {
        ++counters().unsolicited;
        drop(c, kResetDelayNs);
        return;
    }
    const std::size_t used = c.framer.feed(p, n);
    const std::size_t extra = n - used;
    switch (c.framer.state()) {
        case Framer::State::Bad:
            resolve(c, Outcome::Framing);
            drop(c, kResetDelayNs);
            return;
        case Framer::State::Done: {
            const Answer a = c.framer.answer();
            c.framer.reset();
            c.close_after = a.close;
            Outcome o = Outcome::Completed;
            if (a.status != 200) {
                o = Outcome::Status;
            } else if (!a.body_ok) {
                o = Outcome::Body;
            }
            if (o == Outcome::Completed && !sh_.counting && phase_index_ == 1) {
                stats_.latency.add(now >= c.sent_at ? now - c.sent_at : 0);
            }
            resolve(c, o);
            if (extra > 0) {
                ++counters().unsolicited;  // at depth 1 nothing may follow the answer
                drop(c, kResetDelayNs);
            } else if (c.close_after) {
                drop(c, 0);
            } else {
                issue(c, now);
            }
            return;
        }
        case Framer::State::Head:
        case Framer::State::Body: return;  // the answer goes on
    }
}

void Worker::resolve(Conn& c, Outcome o) {
    if (!c.inflight) {
        return;
    }
    c.inflight = false;
    --inflight_;
    Counters& k = counters();
    switch (o) {
        case Outcome::Completed: ++k.completed; break;
        case Outcome::Status: ++k.status; break;
        case Outcome::Body: ++k.body; break;
        case Outcome::Framing: ++k.framing; break;
        case Outcome::Lost: ++k.lost; break;
        case Outcome::Timeout: ++k.timeouts; break;
    }
}

void Worker::drop(Conn& c, std::uint64_t delay_ns) {
    c.state = State::Closing;
    c.drop_delay_ns = delay_ns;
    net_.close(c);
}

void Worker::closed(NetConn& nc, Cause why) {
    Conn& c = static_cast<Conn&>(nc);
    Counters& k = counters();
    std::uint64_t delay = c.drop_delay_ns;
    switch (why) {
        case Cause::Requested: break;
        case Cause::ConnectFailed:
            ++k.connect_errors;
            delay = kConnectErrorDelayNs;
            break;
        case Cause::Reset:
            ++k.resets;
            resolve(c, Outcome::Lost);
            delay = kResetDelayNs;
            break;
        case Cause::PeerClosed:
            ++k.peer_closes;
            resolve(c, Outcome::Lost);
            delay = 0;
            break;
    }
    c.state = State::Closed;
    c.retry_at = clock_ns() + delay;
    c.drop_delay_ns = 0;
    c.framer.reset();
}

// Reconnections and timeouts. Both live here, not in the event paths, so a socket is never made
// again inside the event that closed it.
void Worker::housekeeping(std::uint64_t now) {
    for (int j = 0; j < nconns_; ++j) {
        Conn& c = conns_[static_cast<std::size_t>(j)];
        switch (c.state) {
            case State::Closed:
                if (!c.done && now >= c.retry_at) {
                    start(c, now);
                }
                break;
            case State::Connecting:
                if (now - c.connect_start > timeout_ns_) {
                    ++counters().connect_errors;
                    drop(c, 0);
                }
                break;
            case State::Open:
                if (c.inflight && now - c.last_progress > timeout_ns_) {
                    resolve(c, Outcome::Timeout);
                    drop(c, 0);
                }
                break;
            case State::Closing: break;
        }
    }
}

}  // namespace p2gen
