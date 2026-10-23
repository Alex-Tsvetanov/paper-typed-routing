// The minimal server's I/O on Windows (loop.hpp; design/round3/end-to-end.md, section 7): one
// thread waits on one I/O completion port.
//   - The listener keeps kAccepts AcceptEx calls posted, each with its own socket, and posts a new
//     one whenever one completes.
//   - A connection has one overlapped WSARecv posted while it reads, and at most one WSASend in
//     flight. Its sockets skip the completion packet when an operation completes at once
//     (FILE_SKIP_COMPLETION_PORT_ON_SUCCESS), so that case is handled where the call returns.
//   - Each read is parsed at once and its responses appended to the connection's output buffer
//     (answer_all, the epoll loop's code); the buffer in flight is a second string, so a response
//     appended while a send is in flight never moves the bytes WSASend reads.
//   - A connection is freed only after its socket is closed and no operation of it is in flight.
//   - post_stop() queues a packet with its own key; serve() then closes every socket and waits for
//     the operations in flight to end.
#include "loop.hpp"

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <winsock2.h>
#include <mswsock.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <array>
#include <chrono>
#include <cstring>
#include <ctime>
#include <memory>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>
#include <vector>

#include "http1.hpp"

namespace mserver {

namespace {

[[noreturn]] void fail_wsa(const char* what) {
    throw std::system_error(WSAGetLastError(), std::system_category(), what);
}

[[noreturn]] void fail_win(const char* what) {
    throw std::system_error(static_cast<int>(GetLastError()), std::system_category(), what);
}

constexpr ULONG_PTR kListenKey = 1;
constexpr ULONG_PTR kConnKey = 2;
constexpr ULONG_PTR kStopKey = 3;
constexpr int kAccepts = 16;                          // AcceptEx calls kept posted
constexpr DWORD kAddrLen = sizeof(sockaddr_in) + 16;  // AcceptEx's room for one address

enum class Op : std::uint8_t { Accept, Recv, Send };

// One overlapped operation; OVERLAPPED first, so a completion's pointer is the Io's.
struct Io {
    OVERLAPPED ov{};
    Op op = Op::Recv;
    void* owner = nullptr;
};

struct Conn {
    SOCKET s = INVALID_SOCKET;
    Io recv_io;
    Io send_io;
    std::vector<char> in = std::vector<char>(kConnBuffer);
    std::size_t in_len = 0;
    std::string out;      // responses not yet handed to WSASend
    std::string sending;  // the bytes of the WSASend in flight, from `sent` on
    std::size_t sent = 0;
    bool recv_pending = false;
    bool send_pending = false;
    bool closing = false;      // close once every response is sent
    bool peer_closed = false;  // the peer sent its last byte
};

struct Accept {
    Io io;
    SOCKET s = INVALID_SOCKET;
    bool pending = false;
    char addrs[2 * kAddrLen] = {};
};

bool succeeded(const OVERLAPPED_ENTRY& e) {
    return e.lpOverlapped->Internal == 0;  // the operation's NTSTATUS: STATUS_SUCCESS
}

class Server {
public:
    Server(SOCKET listen_socket, HANDLE port, const Router& router, bool check)
        : listen_(listen_socket), port_(port), router_(router), responses_(check) {
        if (CreateIoCompletionPort(reinterpret_cast<HANDLE>(listen_), port_, kListenKey, 0) == nullptr) {
            fail_win("CreateIoCompletionPort (listener)");
        }
        GUID guid = WSAID_ACCEPTEX;
        DWORD bytes = 0;
        if (WSAIoctl(listen_, SIO_GET_EXTENSION_FUNCTION_POINTER, &guid, sizeof guid, &accept_ex_, sizeof accept_ex_,
                     &bytes, nullptr, nullptr) != 0) {
            fail_wsa("WSAIoctl (AcceptEx)");
        }
        for (int i = 0; i < kAccepts; ++i) {
            auto a = std::make_unique<Accept>();
            a->io.op = Op::Accept;
            a->io.owner = a.get();
            post_accept(*a);
            accepts_.push_back(std::move(a));
        }
    }

    ~Server() {
        for (auto& a : accepts_) {
            if (a->s != INVALID_SOCKET) {
                closesocket(a->s);
            }
        }
        for (auto& c : conns_) {
            if (c->s != INVALID_SOCKET) {
                closesocket(c->s);
            }
        }
    }

    void run() {
        std::array<OVERLAPPED_ENTRY, 64> entries{};
        bool running = true;
        while (running) {
            refresh_date();
            ULONG n = 0;
            if (!GetQueuedCompletionStatusEx(port_, entries.data(), static_cast<ULONG>(entries.size()), &n, 1000,
                                             FALSE)) {
                if (GetLastError() == WAIT_TIMEOUT) {
                    continue;
                }
                fail_win("GetQueuedCompletionStatusEx");
            }
            for (ULONG i = 0; i < n; ++i) {
                if (entries[i].lpCompletionKey == kStopKey) {
                    running = false;
                } else {
                    complete(entries[i], true);
                }
            }
            reap();
        }
        shut_down();
    }

private:
    SOCKET listen_;
    HANDLE port_;
    Router router_;
    Responses responses_;
    RouteResult scratch_;
    LPFN_ACCEPTEX accept_ex_ = nullptr;
    std::time_t date_second_ = -1;
    std::vector<std::unique_ptr<Accept>> accepts_;
    std::vector<std::unique_ptr<Conn>> conns_;
    std::size_t pending_ = 0;  // operations in flight, accepts included

    void refresh_date() {
        const std::time_t now = std::time(nullptr);
        if (now == date_second_) {
            return;
        }
        date_second_ = now;
        std::tm tm{};
        gmtime_s(&tm, &now);
        char buf[32] = {};
        const std::size_t n = std::strftime(buf, sizeof buf, "%a, %d %b %Y %H:%M:%S GMT", &tm);
        responses_.set_date(std::string_view(buf, n));
    }

    void post_accept(Accept& a) {
        a.s = WSASocketW(AF_INET, SOCK_STREAM, IPPROTO_TCP, nullptr, 0, WSA_FLAG_OVERLAPPED);
        if (a.s == INVALID_SOCKET) {
            return;  // posted again when another accept completes
        }
        std::memset(&a.io.ov, 0, sizeof a.io.ov);
        DWORD bytes = 0;
        if (accept_ex_(listen_, a.s, a.addrs, 0, kAddrLen, kAddrLen, &bytes, &a.io.ov) ||
            WSAGetLastError() == ERROR_IO_PENDING) {
            a.pending = true;  // the listener does not skip packets: a completion always comes
            ++pending_;
            return;
        }
        closesocket(a.s);
        a.s = INVALID_SOCKET;
    }

    // One completion. serving: false while shutting down, when nothing new is started.
    void complete(const OVERLAPPED_ENTRY& e, bool serving) {
        Io& io = *reinterpret_cast<Io*>(e.lpOverlapped);
        --pending_;
        const bool ok = succeeded(e);
        if (io.op == Op::Accept) {
            Accept& a = *static_cast<Accept*>(io.owner);
            a.pending = false;
            if (ok && serving) {
                adopt(a.s);
            } else {
                closesocket(a.s);
            }
            a.s = INVALID_SOCKET;
            if (serving) {
                post_accept(a);
            }
            return;
        }
        Conn& c = *static_cast<Conn*>(io.owner);
        if (io.op == Op::Recv) {
            c.recv_pending = false;
            if (!ok) {
                drop(c);
            } else if (serving && c.s != INVALID_SOCKET) {
                on_received(c, e.dwNumberOfBytesTransferred);
                start_recv(c);
            }
            return;
        }
        c.send_pending = false;
        if (!ok) {
            drop(c);
        } else if (serving && c.s != INVALID_SOCKET) {
            c.sent += e.dwNumberOfBytesTransferred;
            start_send(c);
            maybe_close(c);
        }
    }

    void adopt(SOCKET s) {
        setsockopt(s, SOL_SOCKET, SO_UPDATE_ACCEPT_CONTEXT, reinterpret_cast<const char*>(&listen_), sizeof listen_);
        const BOOL one = TRUE;
        setsockopt(s, IPPROTO_TCP, TCP_NODELAY, reinterpret_cast<const char*>(&one), sizeof one);
        if (CreateIoCompletionPort(reinterpret_cast<HANDLE>(s), port_, kConnKey, 0) == nullptr ||
            !SetFileCompletionNotificationModes(reinterpret_cast<HANDLE>(s),
                                                FILE_SKIP_COMPLETION_PORT_ON_SUCCESS | FILE_SKIP_SET_EVENT_ON_HANDLE)) {
            closesocket(s);
            return;
        }
        auto c = std::make_unique<Conn>();
        c->s = s;
        c->recv_io.op = Op::Recv;
        c->recv_io.owner = c.get();
        c->send_io.op = Op::Send;
        c->send_io.owner = c.get();
        c->out.reserve(4096);
        c->sending.reserve(4096);
        Conn& ref = *c;
        conns_.push_back(std::move(c));
        start_recv(ref);
    }

    // Posts a read, and handles every read that completes at once, until one is in flight or the
    // connection stops reading.
    void start_recv(Conn& c) {
        while (c.s != INVALID_SOCKET && !c.recv_pending && !c.closing && !c.peer_closed && c.in_len < kConnBuffer) {
            WSABUF b{static_cast<ULONG>(kConnBuffer - c.in_len), c.in.data() + c.in_len};
            DWORD n = 0;
            DWORD flags = 0;
            std::memset(&c.recv_io.ov, 0, sizeof c.recv_io.ov);
            if (WSARecv(c.s, &b, 1, &n, &flags, &c.recv_io.ov, nullptr) == 0) {
                on_received(c, n);  // completed at once: no packet comes
                continue;
            }
            if (WSAGetLastError() == WSA_IO_PENDING) {
                c.recv_pending = true;
                ++pending_;
                return;
            }
            drop(c);
            return;
        }
    }

    void on_received(Conn& c, DWORD n) {
        if (n == 0) {
            c.peer_closed = true;
        } else {
            c.in_len += n;
            const std::size_t off = answer_all(std::string_view(c.in.data(), c.in_len), c.in_len == kConnBuffer,
                                               responses_, router_, scratch_, c.out, c.closing);
            if (off != 0) {
                std::memmove(c.in.data(), c.in.data() + off, c.in_len - off);
                c.in_len -= off;
            }
        }
        start_send(c);
        maybe_close(c);
    }

    // Hands the output to WSASend, one buffer at a time, until a send is in flight or nothing is left.
    void start_send(Conn& c) {
        while (c.s != INVALID_SOCKET && !c.send_pending) {
            if (c.sent == c.sending.size()) {
                if (c.out.empty()) {
                    return;
                }
                c.sending.clear();
                c.sent = 0;
                std::swap(c.sending, c.out);
            }
            WSABUF b{static_cast<ULONG>(c.sending.size() - c.sent), c.sending.data() + c.sent};
            DWORD n = 0;
            std::memset(&c.send_io.ov, 0, sizeof c.send_io.ov);
            if (WSASend(c.s, &b, 1, &n, 0, &c.send_io.ov, nullptr) == 0) {
                c.sent += n;  // completed at once: no packet comes
                continue;
            }
            if (WSAGetLastError() == WSA_IO_PENDING) {
                c.send_pending = true;
                ++pending_;
                return;
            }
            drop(c);
            return;
        }
    }

    void maybe_close(Conn& c) {
        if (c.s != INVALID_SOCKET && (c.closing || c.peer_closed) && !c.send_pending && c.sent == c.sending.size() &&
            c.out.empty()) {
            drop(c);
        }
    }

    // Closes the socket; operations in flight then complete with an error, and reap() frees the
    // connection once none is left.
    void drop(Conn& c) {
        if (c.s != INVALID_SOCKET) {
            closesocket(c.s);
            c.s = INVALID_SOCKET;
        }
    }

    void reap() {
        for (std::size_t i = 0; i < conns_.size();) {
            const Conn& c = *conns_[i];
            if (c.s == INVALID_SOCKET && !c.recv_pending && !c.send_pending) {
                conns_[i] = std::move(conns_.back());
                conns_.pop_back();
            } else {
                ++i;
            }
        }
    }

    // Closes every socket, then waits until every operation in flight has completed (they complete
    // with an error once their socket is closed), at most 5 s.
    void shut_down() {
        CancelIoEx(reinterpret_cast<HANDLE>(listen_), nullptr);
        for (auto& a : accepts_) {
            if (a->s != INVALID_SOCKET && !a->pending) {
                closesocket(a->s);
                a->s = INVALID_SOCKET;
            }
        }
        for (auto& c : conns_) {
            drop(*c);
        }
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
        std::array<OVERLAPPED_ENTRY, 64> entries{};
        while (pending_ > 0 && std::chrono::steady_clock::now() < deadline) {
            ULONG n = 0;
            if (!GetQueuedCompletionStatusEx(port_, entries.data(), static_cast<ULONG>(entries.size()), &n, 100,
                                             FALSE)) {
                continue;
            }
            for (ULONG i = 0; i < n; ++i) {
                if (entries[i].lpCompletionKey != kStopKey) {
                    complete(entries[i], false);
                }
            }
        }
        reap();
    }
};

}  // namespace

Listener listen_loopback(std::uint16_t port) {
    const SOCKET s = WSASocketW(AF_INET, SOCK_STREAM, IPPROTO_TCP, nullptr, 0, WSA_FLAG_OVERLAPPED);
    if (s == INVALID_SOCKET) {
        fail_wsa("WSASocketW");
    }
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_port = htons(port);
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(s, reinterpret_cast<const sockaddr*>(&a), sizeof a) != 0 || listen(s, SOMAXCONN) != 0) {
        const int e = WSAGetLastError();
        closesocket(s);
        throw std::system_error(e, std::system_category(), "bind or listen");
    }
    int len = sizeof a;
    getsockname(s, reinterpret_cast<sockaddr*>(&a), &len);
    return {static_cast<std::uintptr_t>(s), ntohs(a.sin_port)};
}

std::uintptr_t make_port() {
    const HANDLE port = CreateIoCompletionPort(INVALID_HANDLE_VALUE, nullptr, 0, 1);
    if (port == nullptr) {
        fail_win("CreateIoCompletionPort");
    }
    return reinterpret_cast<std::uintptr_t>(port);
}

void post_stop(std::uintptr_t port) noexcept {
    PostQueuedCompletionStatus(reinterpret_cast<HANDLE>(port), 0, kStopKey, nullptr);
}

void serve(const Listener& listener, std::uintptr_t port, const Router& router, bool check) {
    Server s(static_cast<SOCKET>(listener.socket), reinterpret_cast<HANDLE>(port), router, check);
    s.run();
}

}  // namespace mserver
