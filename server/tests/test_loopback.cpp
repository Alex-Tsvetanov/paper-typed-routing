// Loopback tests of the minimal server's I/O loop (server/src/loop.hpp) over raw sockets
// (design/round2/minimal-server.md, section 5): byte-exact answers, HEAD then GET on one
// keep-alive connection, pipelined requests in order, a split request, Connection: close, the
// refusals, a skipped body, many connections, a peer that closes its sending side, answers larger
// than the socket buffers read slowly, and a clean stop. No test framework. The same cases run
// against the epoll loop on Linux and the I/O completion port loop on Windows; the few
// system-specific calls are the small wrappers below. These are functional tests: nothing is timed.
#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/eventfd.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#endif

#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

#include "loop.hpp"

namespace {

int g_failures = 0;

#define CHECK(cond)                                                                   \
    do {                                                                              \
        if (!(cond)) {                                                                \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
            ++g_failures;                                                             \
        }                                                                             \
    } while (0)

using namespace mserver;

// ---- the system-specific calls -------------------------------------------------------------

#if defined(_WIN32)

using sock_t = SOCKET;
constexpr sock_t kBadSock = INVALID_SOCKET;

void sock_init() {
    WSADATA data;
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
        std::fprintf(stderr, "test_loopback: WSAStartup failed\n");
        std::exit(2);
    }
}
void sock_cleanup() { WSACleanup(); }
void sock_close(sock_t s) { closesocket(s); }
// Bytes sent (at most 1 MiB per call, lengths being int here), or <= 0 on failure.
std::ptrdiff_t sock_send(sock_t s, const char* p, std::size_t n) {
    return send(s, p, static_cast<int>(std::min<std::size_t>(n, std::size_t{1} << 20)), 0);
}
std::ptrdiff_t sock_recv(sock_t s, char* p, std::size_t n) { return recv(s, p, static_cast<int>(n), 0); }
// Whether the socket is readable (or hung up) within `ms`.
bool wait_readable(sock_t s, int ms) {
    WSAPOLLFD p{s, POLLIN, 0};
    return WSAPoll(&p, 1, ms) > 0;
}
void half_close(sock_t s) { shutdown(s, SD_SEND); }
void set_recv_buffer(sock_t s, int bytes) {
    setsockopt(s, SOL_SOCKET, SO_RCVBUF, reinterpret_cast<const char*>(&bytes), sizeof bytes);
}
void set_send_timeout(sock_t s, int ms) {
    const DWORD t = static_cast<DWORD>(ms);
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, reinterpret_cast<const char*>(&t), sizeof t);
}

#else

using sock_t = int;
constexpr sock_t kBadSock = -1;

void sock_init() {}
void sock_cleanup() {}
void sock_close(sock_t s) { close(s); }
std::ptrdiff_t sock_send(sock_t s, const char* p, std::size_t n) { return send(s, p, n, MSG_NOSIGNAL); }
std::ptrdiff_t sock_recv(sock_t s, char* p, std::size_t n) { return recv(s, p, n, 0); }
bool wait_readable(sock_t s, int ms) {
    pollfd p{s, POLLIN, 0};
    return poll(&p, 1, ms) > 0;
}
void half_close(sock_t s) { shutdown(s, SHUT_WR); }
void set_recv_buffer(sock_t s, int bytes) { setsockopt(s, SOL_SOCKET, SO_RCVBUF, &bytes, sizeof bytes); }
void set_send_timeout(sock_t s, int ms) {
    timeval t{};
    t.tv_sec = ms / 1000;
    t.tv_usec = (ms % 1000) * 1000;
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &t, sizeof t);
}

#endif

bool valid(sock_t s) { return s != kBadSock; }

// ---- the router -----------------------------------------------------------------------------

struct Route {
    unsigned method;
    std::string path;
};
std::vector<Route> g_routes = {{kGet, "/"}, {kGet, "/a"}, {kPost, "/p"}, {kHead, "/h"}};

void find(const void*, unsigned method, const std::string& path, RouteResult& out) {
    out.count = 0;
    out.allowed = 0;
    for (std::size_t i = 0; i < g_routes.size(); ++i) {
        if (g_routes[i].path == path && g_routes[i].method == method) {
            out.status = RouteStatus::Found;
            out.route = static_cast<std::uint32_t>(i);
            return;
        }
    }
    for (const Route& r : g_routes) {
        if (r.path == path) {
            out.allowed = static_cast<std::uint16_t>(out.allowed | (1u << r.method));
        }
    }
    out.status = out.allowed ? RouteStatus::MethodNotAllowed : RouteStatus::NotFound;
}

// ---- the client -----------------------------------------------------------------------------

// recv_buffer > 0: the socket's receive buffer, set before connecting so that it bounds the window.
sock_t connect_to(std::uint16_t port, int recv_buffer = 0) {
    const sock_t fd = socket(AF_INET, SOCK_STREAM, 0);
    if (!valid(fd)) {
        return kBadSock;
    }
    if (recv_buffer > 0) {
        set_recv_buffer(fd, recv_buffer);
    }
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_port = htons(port);
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) != 0) {
        sock_close(fd);
        return kBadSock;
    }
    return fd;
}

// Whether every byte went out.
bool send_all(sock_t fd, std::string_view s) {
    while (!s.empty()) {
        const std::ptrdiff_t n = sock_send(fd, s.data(), s.size());
        if (n <= 0) {
            return false;
        }
        s.remove_prefix(static_cast<std::size_t>(n));
    }
    return true;
}

// Reads until `want` bytes have arrived, the peer closes, or 2 s pass. closed: whether the peer
// closed (after the bytes read).
std::string read_some(sock_t fd, std::size_t want, bool* closed = nullptr) {
    std::string got;
    const auto until = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    if (closed) {
        *closed = false;
    }
    while (got.size() < want && std::chrono::steady_clock::now() < until) {
        if (!wait_readable(fd, 100)) {
            continue;
        }
        char buf[4096];
        const std::ptrdiff_t n = sock_recv(fd, buf, sizeof buf);
        if (n <= 0) {
            if (closed) {
                *closed = true;
            }
            break;
        }
        got.append(buf, static_cast<std::size_t>(n));
    }
    return got;
}

// Whether the peer closes within 2 s, with no more bytes.
bool closes(sock_t fd) {
    bool closed = false;
    const std::string more = read_some(fd, 1, &closed);
    return more.empty() && closed;
}

// Reads `want` bytes in small pieces with short pauses, so that the server's output backs up
// against the socket's buffers; gives up after 30 s. closed: whether the peer closed first.
std::string read_slowly(sock_t fd, std::size_t want, bool* closed) {
    std::string got;
    got.reserve(want);
    *closed = false;
    const auto until = std::chrono::steady_clock::now() + std::chrono::seconds(30);
    char buf[2048];
    unsigned reads = 0;
    while (got.size() < want && std::chrono::steady_clock::now() < until) {
        if (!wait_readable(fd, 100)) {
            continue;
        }
        const std::ptrdiff_t n = sock_recv(fd, buf, sizeof buf);
        if (n <= 0) {
            *closed = true;
            break;
        }
        got.append(buf, static_cast<std::size_t>(n));
        if (++reads % 32 == 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
    return got;
}

// The Date field's value replaced by a fixed one, so that responses compare byte for byte.
std::string undated(std::string s) {
    for (std::size_t at = s.find("Date: "); at != std::string::npos; at = s.find("Date: ", at + 1)) {
        if (at + 6 + 29 <= s.size()) {
            s.replace(at + 6, 29, "Thu, 01 Jan 1970 00:00:00 GMT");
        }
    }
    return s;
}

std::string escaped(std::string_view s) {
    std::string out;
    for (const char ch : s) {
        const auto c = static_cast<unsigned char>(ch);
        if (c == '\r') {
            out += "\\r";
        } else if (c == '\n') {
            out += "\\n";
        } else if (c >= 0x20 && c < 0x7f) {
            out += ch;
        } else {
            char hex[8];
            std::snprintf(hex, sizeof hex, "\\x%02x", c);
            out += hex;
        }
    }
    return out;
}

// Compares two byte strings; on a difference prints the sizes, the first differing offset and the
// bytes there, so that a failure shows what arrived.
bool same_bytes(const char* what, const std::string& got, const std::string& want) {
    if (got == want) {
        return true;
    }
    std::size_t at = 0;
    while (at < got.size() && at < want.size() && got[at] == want[at]) {
        ++at;
    }
    std::fprintf(stderr, "%s: got %zu bytes, want %zu, first difference at offset %zu\n", what, got.size(),
                 want.size(), at);
    std::fprintf(stderr, "  got : %s\n", escaped(std::string_view(got).substr(at, 64)).c_str());
    std::fprintf(stderr, "  want: %s\n", escaped(std::string_view(want).substr(at, 64)).c_str());
    return false;
}

const std::string kD = "Thu, 01 Jan 1970 00:00:00 GMT";
const std::string kOkHead = "HTTP/1.1 200 OK\r\nDate: " + kD + "\r\nContent-Type: text/plain\r\nContent-Length: 13\r\n\r\n";
const std::string kOk = kOkHead + "Hello, World!";
const std::string kNotFound = "HTTP/1.1 404 Not Found\r\nDate: " + kD + "\r\nContent-Length: 0\r\n\r\n";

// ---- the cases ------------------------------------------------------------------------------

void test_answers(std::uint16_t port) {
    const sock_t fd = connect_to(port);
    CHECK(valid(fd));
    send_all(fd, "GET /a HTTP/1.1\r\nHost: t\r\n\r\n");
    CHECK(undated(read_some(fd, kOk.size())) == kOk);
    // HEAD, then GET, on the same connection: the HEAD response has no content, so the GET
    // response follows it directly.
    send_all(fd, "HEAD /a HTTP/1.1\r\n\r\n");
    CHECK(undated(read_some(fd, kOkHead.size())) == kOkHead);
    send_all(fd, "GET /a HTTP/1.1\r\n\r\n");
    CHECK(undated(read_some(fd, kOk.size())) == kOk);
    // Three pipelined requests, answered in order.
    send_all(fd, "GET /a HTTP/1.1\r\n\r\nGET /none HTTP/1.1\r\n\r\nHEAD /a HTTP/1.1\r\n\r\n");
    const std::string three = kOk + kNotFound + kOkHead;
    CHECK(undated(read_some(fd, three.size())) == three);
    // A request in two parts.
    send_all(fd, "GET /a HT");
    std::this_thread::sleep_for(std::chrono::milliseconds(30));
    send_all(fd, "TP/1.1\r\n\r\n");
    CHECK(undated(read_some(fd, kOk.size())) == kOk);
    // A body of Content-Length bytes is skipped.
    const std::string na = "HTTP/1.1 405 Method Not Allowed\r\nDate: " + kD + "\r\nContent-Length: 0\r\nAllow: POST\r\n\r\n";
    send_all(fd, "PUT /p HTTP/1.1\r\nContent-Length: 5\r\n\r\nhelloGET /a HTTP/1.1\r\n\r\n");
    CHECK(undated(read_some(fd, na.size() + kOk.size())) == na + kOk);
    // Connection: close: the response, then the server closes.
    send_all(fd, "GET /a HTTP/1.1\r\nConnection: close\r\n\r\n");
    const std::string closing = kOkHead.substr(0, kOkHead.size() - 2) + "Connection: close\r\n\r\nHello, World!";
    CHECK(undated(read_some(fd, closing.size())) == closing);
    CHECK(closes(fd));
    sock_close(fd);
}

void test_closing(std::uint16_t port) {
    // HTTP/1.0 without keep-alive.
    sock_t fd = connect_to(port);
    send_all(fd, "GET / HTTP/1.0\r\n\r\n");
    const std::string h10 = kOkHead.substr(0, kOkHead.size() - 2) + "Connection: close\r\n\r\nHello, World!";
    CHECK(undated(read_some(fd, h10.size())) == h10);
    CHECK(closes(fd));
    sock_close(fd);
    // Refusals: 431 for a head over 8 KiB, 501 for a transfer coding; then the server closes.
    fd = connect_to(port);
    send_all(fd, "GET /a HTTP/1.1\r\nX: " + std::string(9000, 'a'));
    const std::string r431 = "HTTP/1.1 431 Request Header Fields Too Large\r\nDate: " + kD +
                             "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    CHECK(undated(read_some(fd, r431.size())) == r431);
    CHECK(closes(fd));
    sock_close(fd);
    fd = connect_to(port);
    send_all(fd, "POST /p HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n");
    const std::string r501 =
        "HTTP/1.1 501 Not Implemented\r\nDate: " + kD + "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    CHECK(undated(read_some(fd, r501.size())) == r501);
    CHECK(closes(fd));
    sock_close(fd);
    // A body larger than the connection's buffer: 413, then the server closes.
    fd = connect_to(port);
    send_all(fd, "POST /p HTTP/1.1\r\nContent-Length: " + std::to_string(kConnBuffer) + "\r\n\r\n" + std::string(kConnBuffer, 'b'));
    const std::string r413 = "HTTP/1.1 413 Content Too Large\r\nDate: " + kD + "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    CHECK(same_bytes("413", undated(read_some(fd, r413.size())), r413));
    sock_close(fd);
}

void test_many_connections(std::uint16_t port) {
    std::vector<sock_t> fds;
    for (int i = 0; i < 64; ++i) {
        fds.push_back(connect_to(port));
    }
    for (const sock_t fd : fds) {
        send_all(fd, "GET /a HTTP/1.1\r\n\r\n");
    }
    int answered = 0;
    for (const sock_t fd : fds) {
        answered += undated(read_some(fd, kOk.size())) == kOk;
        sock_close(fd);
    }
    CHECK(answered == 64);
}

// The client closes its sending side: the server still answers what it has read, then closes.
void test_half_close(std::uint16_t port) {
    // One request, then the end of the client's stream.
    sock_t fd = connect_to(port);
    CHECK(valid(fd));
    CHECK(send_all(fd, "GET /a HTTP/1.1\r\n\r\n"));
    half_close(fd);
    CHECK(undated(read_some(fd, kOk.size())) == kOk);
    CHECK(closes(fd));
    sock_close(fd);
    // Pipelined requests, then the end of the stream: every answer, in order, then the close.
    fd = connect_to(port);
    CHECK(valid(fd));
    CHECK(send_all(fd, "GET /a HTTP/1.1\r\n\r\nGET /none HTTP/1.1\r\n\r\nHEAD /a HTTP/1.1\r\n\r\n"));
    half_close(fd);
    const std::string three = kOk + kNotFound + kOkHead;
    CHECK(undated(read_some(fd, three.size())) == three);
    CHECK(closes(fd));
    sock_close(fd);
    // Half a request, then the end of the stream: nothing to answer, the server closes.
    fd = connect_to(port);
    CHECK(valid(fd));
    CHECK(send_all(fd, "GET /a HT"));
    half_close(fd);
    CHECK(closes(fd));
    sock_close(fd);
}

// Pipelines requests whose answers together are several times larger than any socket buffer, with
// a small receive buffer on the client and a slow reader, so that the server's output backs up and
// is sent in pieces while more answers are appended behind it. A fixed pseudo-random mix of three
// kinds of request makes every position in the output distinct, so that an answer out of order,
// lost or repeated shows. half: the client also closes its sending side after the last request.
void test_large_pipeline(std::uint16_t port, bool half) {
    constexpr std::size_t kRequests = 60000;
    const std::array<std::pair<std::string_view, const std::string*>, 3> kinds{{
        {"GET /a HTTP/1.1\r\n\r\n", &kOk},
        {"GET /none HTTP/1.1\r\n\r\n", &kNotFound},
        {"HEAD /a HTTP/1.1\r\n\r\n", &kOkHead},
    }};
    std::string requests;
    std::string want;
    std::uint32_t x = 2463534242u;  // xorshift32
    for (std::size_t i = 0; i < kRequests; ++i) {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        const auto& kind = kinds[x % kinds.size()];
        requests += kind.first;
        want += *kind.second;
    }
    const sock_t fd = connect_to(port, 4096);
    CHECK(valid(fd));
    if (!valid(fd)) {
        return;
    }
    set_send_timeout(fd, 10000);  // a server that stops reading fails the case instead of hanging it
    CHECK(send_all(fd, requests));
    if (half) {
        half_close(fd);
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(200));  // let the output back up
    bool closed = false;
    const std::string got = undated(read_slowly(fd, want.size(), &closed));
    CHECK(same_bytes(half ? "large pipeline, half-closed" : "large pipeline", got, want));
    if (half) {
        CHECK(closes(fd));  // the server closes after the last answer
    } else {
        // Still open and in step: no stray bytes ahead of the next answer.
        CHECK(send_all(fd, "GET /a HTTP/1.1\r\n\r\n"));
        CHECK(undated(read_some(fd, kOk.size())) == kOk);
    }
    sock_close(fd);
}

}  // namespace

int main() {
    sock_init();
    const Router router{find, nullptr};
#if defined(_WIN32)
    const Listener l = listen_loopback(0);
    CHECK(l.socket != INVALID_SOCKET && l.port != 0);
    const std::uintptr_t stop = make_port();
    std::thread worker([&] { serve(l, stop, router); });
#else
    const Listener l = listen_loopback(0);
    CHECK(l.fd >= 0 && l.port != 0);
    const int stop = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
    std::thread worker([&] { serve(l.fd, stop, router); });
#endif
    test_answers(l.port);
    test_closing(l.port);
    test_many_connections(l.port);
    test_half_close(l.port);
    test_large_pipeline(l.port, false);
    test_large_pipeline(l.port, true);
    // A clean stop: serve returns, and an open connection is closed.
    const sock_t idle = connect_to(l.port);
#if defined(_WIN32)
    post_stop(stop);
    worker.join();
    CHECK(closes(idle));
    sock_close(idle);
    CloseHandle(reinterpret_cast<HANDLE>(stop));
    closesocket(static_cast<SOCKET>(l.socket));
#else
    const std::uint64_t one = 1;
    CHECK(write(stop, &one, sizeof one) == sizeof one);
    worker.join();
    CHECK(closes(idle));
    sock_close(idle);
    close(stop);
    close(l.fd);
#endif
    sock_cleanup();
    if (g_failures == 0) {
        std::printf("test_loopback: all checks passed\n");
    }
    return g_failures == 0 ? 0 : 1;
}
