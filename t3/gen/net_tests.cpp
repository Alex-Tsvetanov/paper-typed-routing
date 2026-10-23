// Tests of p2gen's network backend alone (net.hpp), against a plain blocking server socket kept
// by the test. They cover what the generator's own runs cannot force: a request sent while the one
// before it is still being written. The generator has one request in flight, but an answer can be
// taken before the completion of the send of its request, so the backend must hold the next
// request and send it after the first, whole and in order, also when the first is larger than
// the socket buffers and goes out in pieces. A second waiting request is a misuse and fails the
// connection. Functional tests: nothing here is timed. No test framework.
#include <atomic>
#include <chrono>
#include <cstdio>
#include <functional>
#include <string>
#include <thread>
#include <vector>

#include "net.hpp"

#if !defined(_WIN32)
#include <arpa/inet.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace {

using namespace p2gen;

int g_failures = 0;

#define CHECK(cond)                                                                       \
    do {                                                                                  \
        if (!(cond)) {                                                                    \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
            ++g_failures;                                                                 \
        }                                                                                 \
    } while (0)

// ---- the system-specific calls -------------------------------------------------------------

#if defined(_WIN32)
using Sock = SOCKET;
constexpr Sock kNoSock = INVALID_SOCKET;
void close_sock(Sock s) {
    closesocket(s);
}
#else
using Sock = int;
constexpr Sock kNoSock = -1;
void close_sock(Sock s) {
    ::close(s);
}
#endif

// A listening socket on 127.0.0.1 and a free port.
Sock listen_loopback(int& port) {
    const Sock s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    a.sin_port = 0;
    if (s == kNoSock || bind(s, reinterpret_cast<const sockaddr*>(&a), sizeof a) != 0 || listen(s, 8) != 0) {
        return kNoSock;
    }
    socklen_t len = sizeof a;
    getsockname(s, reinterpret_cast<sockaddr*>(&a), &len);
    port = ntohs(a.sin_port);
    return s;
}

bool readable_within(Sock s, int ms) {
    fd_set set;
    FD_ZERO(&set);
    FD_SET(s, &set);
    timeval tv{};
    tv.tv_sec = ms / 1000;
    tv.tv_usec = (ms % 1000) * 1000;
    return select(static_cast<int>(s) + 1, &set, nullptr, nullptr, &tv) > 0;
}

// ---- the server of the tests ---------------------------------------------------------------

// Accepts one connection, waits delay_ms, then reads until `want` bytes, the end of the
// connection, or a stall of 10 s.
class Collector {
public:
    Collector(std::size_t want, int delay_ms) : want_(want), delay_ms_(delay_ms) {
        listener_ = listen_loopback(port_);
    }
    ~Collector() {
        if (thread_.joinable()) {
            thread_.join();
        }
        if (listener_ != kNoSock) {
            close_sock(listener_);
        }
    }
    bool ok() const { return listener_ != kNoSock; }
    int port() const { return port_; }
    void start() { thread_ = std::thread([this] { run(); }); }
    bool finished() const { return finished_.load(); }
    // Joins and returns what arrived.
    const std::string& received() {
        if (thread_.joinable()) {
            thread_.join();
        }
        return got_;
    }

private:
    void run() {
        if (readable_within(listener_, 10000)) {
            const Sock c = accept(listener_, nullptr, nullptr);
            if (c != kNoSock) {
                std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms_));
                std::vector<char> buf(262144);
                while (got_.size() < want_ && readable_within(c, 10000)) {
                    const int n = static_cast<int>(recv(c, buf.data(), static_cast<int>(buf.size()), 0));
                    if (n <= 0) {
                        break;
                    }
                    got_.append(buf.data(), static_cast<std::size_t>(n));
                }
                close_sock(c);
            }
        }
        finished_.store(true);
    }

    std::size_t want_;
    int delay_ms_;
    int port_ = 0;
    Sock listener_ = kNoSock;
    std::string got_;
    std::atomic<bool> finished_{false};
    std::thread thread_;
};

// ---- the client side -----------------------------------------------------------------------

struct Probe final : NetHandler {
    std::function<void(NetConn&)> on_connected;
    bool closed_seen = false;
    Cause cause = Cause::Requested;

    bool begin_batch() override { return true; }
    void connected(NetConn& c) override {
        if (on_connected) {
            on_connected(c);
        }
    }
    void data(NetConn&, const char*, std::size_t) override {}
    void closed(NetConn&, Cause why) override {
        closed_seen = true;
        cause = why;
    }
};

// Waits on the backend until done() or a generous bound of waits.
bool pump(Net& net, const std::function<bool()>& done) {
    for (int i = 0; i < 6000; ++i) {
        net.poll(5);
        if (done()) {
            return true;
        }
    }
    return false;
}

std::string pattern(std::size_t from, std::size_t n) {
    std::string s(n, ' ');
    for (std::size_t i = 0; i < n; ++i) {
        s[i] = static_cast<char>('a' + (from + i) % 23);
    }
    return s;
}

// ---- the tests -----------------------------------------------------------------------------

// First and second request sent from one callback, as when an answer is taken before the
// completion of the send of its request. first_bytes: the size of the first; server_delay_ms: how
// long the server waits before it reads, so that a large first request is still being written.
void two_requests(std::size_t first_bytes, int server_delay_ms) {
    const std::string a = pattern(0, first_bytes);
    const std::string b = pattern(first_bytes, 1000);
    Collector srv(a.size() + b.size(), server_delay_ms);
    CHECK(srv.ok());
    if (!srv.ok()) {
        return;
    }
    srv.start();
    sockaddr_in addr{};
    CHECK(make_address("127.0.0.1", srv.port(), addr));

    Probe probe;
    Net net(probe, addr);
    CHECK(net.init());
    NetConn c;
    probe.on_connected = [&](NetConn& nc) {
        net.send(nc, a.data(), a.size());
        net.send(nc, b.data(), b.size());  // held until the first is written
    };
    net.connect(c);
    CHECK(pump(net, [&] { return srv.finished(); }));
    net.close(c);
    CHECK(net.drain(5000));
    const std::string& got = srv.received();
    CHECK(got.size() == a.size() + b.size());
    CHECK(got == a + b);
    // The server closes when it has everything: a close by the peer is right, a reset is not.
    CHECK(!probe.closed_seen || probe.cause == Cause::PeerClosed || probe.cause == Cause::Requested);
}

// A second request waiting behind the first is a misuse: the connection fails with Reset.
void third_request_is_refused() {
    const std::string a = pattern(0, 16 * 1024 * 1024);
    const std::string b = pattern(1, 1000);
    Collector srv(a.size() + 2000, 300);
    CHECK(srv.ok());
    if (!srv.ok()) {
        return;
    }
    srv.start();
    sockaddr_in addr{};
    CHECK(make_address("127.0.0.1", srv.port(), addr));

    Probe probe;
    Net net(probe, addr);
    CHECK(net.init());
    NetConn c;
    probe.on_connected = [&](NetConn& nc) {
        net.send(nc, a.data(), a.size());
        net.send(nc, b.data(), b.size());
        net.send(nc, b.data(), b.size());  // a second one waiting
    };
    net.connect(c);
    CHECK(pump(net, [&] { return probe.closed_seen; }));
    CHECK(probe.closed_seen && probe.cause == Cause::Reset);
    net.close(c);
    CHECK(net.drain(5000));
    srv.received();
}

}  // namespace

int main() {
    NetRuntime runtime;
    CHECK(runtime.ok());
    two_requests(200, 0);                     // both fit in the socket at once
    two_requests(16 * 1024 * 1024, 300);      // the first goes out in pieces while the server waits
    third_request_is_refused();
    if (g_failures != 0) {
        std::fprintf(stderr, "p2gen_net_tests: %d check(s) failed\n", g_failures);
        return 1;
    }
    std::printf("p2gen_net_tests: all checks passed\n");
    return 0;
}
