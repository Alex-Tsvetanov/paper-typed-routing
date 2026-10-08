// Loopback tests of the minimal server's I/O loop (server/src/loop.hpp) over raw sockets
// (design/round2/minimal-server.md, section 5): byte-exact answers, HEAD then GET on one
// keep-alive connection, pipelined requests in order, a split request, Connection: close, the
// refusals, a skipped body, many connections, and a clean stop. No test framework.
#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/eventfd.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <cstdio>
#include <cstring>
#include <string>
#include <string_view>
#include <thread>
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

struct Route {
    unsigned method;
    std::string path;
};
std::vector<Route> g_routes = {{kGet, "/"}, {kGet, "/a"}, {kPost, "/p"}, {kHead, "/h"}};

void find(const void*, unsigned method, std::string_view path, RouteResult& out) {
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

int connect_to(std::uint16_t port) {
    const int fd = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_port = htons(port);
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

void send_all(int fd, std::string_view s) {
    while (!s.empty()) {
        const ssize_t n = send(fd, s.data(), s.size(), MSG_NOSIGNAL);
        if (n <= 0) {
            return;
        }
        s.remove_prefix(static_cast<std::size_t>(n));
    }
}

// Reads until `want` bytes have arrived, the peer closes, or 2 s pass. closed: whether the peer
// closed (after the bytes read).
std::string read_some(int fd, std::size_t want, bool* closed = nullptr) {
    std::string got;
    const auto until = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    if (closed) {
        *closed = false;
    }
    while (got.size() < want && std::chrono::steady_clock::now() < until) {
        pollfd p{fd, POLLIN, 0};
        if (poll(&p, 1, 100) <= 0) {
            continue;
        }
        char buf[4096];
        const ssize_t n = recv(fd, buf, sizeof buf, 0);
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
bool closes(int fd) {
    bool closed = false;
    const std::string more = read_some(fd, 1, &closed);
    return more.empty() && closed;
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

const std::string kD = "Thu, 01 Jan 1970 00:00:00 GMT";
const std::string kOkHead = "HTTP/1.1 200 OK\r\nDate: " + kD + "\r\nContent-Type: text/plain\r\nContent-Length: 13\r\n\r\n";
const std::string kOk = kOkHead + "Hello, World!";
const std::string kNotFound = "HTTP/1.1 404 Not Found\r\nDate: " + kD + "\r\nContent-Length: 0\r\n\r\n";

void test_answers(std::uint16_t port) {
    const int fd = connect_to(port);
    CHECK(fd >= 0);
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
    close(fd);
}

void test_closing(std::uint16_t port) {
    // HTTP/1.0 without keep-alive.
    int fd = connect_to(port);
    send_all(fd, "GET / HTTP/1.0\r\n\r\n");
    const std::string h10 = kOkHead.substr(0, kOkHead.size() - 2) + "Connection: close\r\n\r\nHello, World!";
    CHECK(undated(read_some(fd, h10.size())) == h10);
    CHECK(closes(fd));
    close(fd);
    // Refusals: 431 for a head over 8 KiB, 501 for a transfer coding; then the server closes.
    fd = connect_to(port);
    send_all(fd, "GET /a HTTP/1.1\r\nX: " + std::string(9000, 'a'));
    const std::string r431 = "HTTP/1.1 431 Request Header Fields Too Large\r\nDate: " + kD +
                             "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    CHECK(undated(read_some(fd, r431.size())) == r431);
    CHECK(closes(fd));
    close(fd);
    fd = connect_to(port);
    send_all(fd, "POST /p HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n");
    const std::string r501 =
        "HTTP/1.1 501 Not Implemented\r\nDate: " + kD + "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    CHECK(undated(read_some(fd, r501.size())) == r501);
    CHECK(closes(fd));
    close(fd);
    // A body larger than the connection's buffer: 413, then the server closes.
    fd = connect_to(port);
    send_all(fd, "POST /p HTTP/1.1\r\nContent-Length: " + std::to_string(kConnBuffer) + "\r\n\r\n" + std::string(kConnBuffer, 'b'));
    const std::string r413 = "HTTP/1.1 413 Content Too Large\r\nDate: " + kD + "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    CHECK(undated(read_some(fd, r413.size())) == r413);
    close(fd);
}

void test_many_connections(std::uint16_t port) {
    std::vector<int> fds;
    for (int i = 0; i < 64; ++i) {
        fds.push_back(connect_to(port));
    }
    for (const int fd : fds) {
        send_all(fd, "GET /a HTTP/1.1\r\n\r\n");
    }
    int answered = 0;
    for (const int fd : fds) {
        answered += undated(read_some(fd, kOk.size())) == kOk;
        close(fd);
    }
    CHECK(answered == 64);
}

}  // namespace

int main() {
    const Listener l = listen_loopback(0);
    CHECK(l.fd >= 0 && l.port != 0);
    const int stop = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
    const Router router{find, nullptr};
    std::thread worker([&] { serve(l.fd, stop, router); });
    test_answers(l.port);
    test_closing(l.port);
    test_many_connections(l.port);
    // A clean stop: serve returns, and an open connection is closed.
    const int idle = connect_to(l.port);
    const std::uint64_t one = 1;
    CHECK(write(stop, &one, sizeof one) == sizeof one);
    worker.join();
    CHECK(closes(idle));
    close(idle);
    close(stop);
    close(l.fd);
    if (g_failures == 0) {
        std::printf("test_loopback: all checks passed\n");
    }
    return g_failures == 0 ? 0 : 1;
}
