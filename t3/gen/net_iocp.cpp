#include "net.hpp"

#include <chrono>
#include <cstring>

namespace p2gen {

namespace {
constexpr ULONG kMaxEntries = 64;
constexpr DWORD kDrainStepMs = 50;
}  // namespace

bool make_address(const std::string& host, int port, sockaddr_in& out) {
    out = sockaddr_in{};
    out.sin_family = AF_INET;
    out.sin_port = htons(static_cast<u_short>(port));
    return inet_pton(AF_INET, host.c_str(), &out.sin_addr) == 1;
}

bool pin_current_thread(int cpu) {
    if (cpu < 0 || cpu > 63) {
        return false;
    }
    return SetThreadAffinityMask(GetCurrentThread(), static_cast<DWORD_PTR>(1) << cpu) != 0;
}

NetRuntime::NetRuntime() {
    WSADATA wsa{};
    ok_ = WSAStartup(MAKEWORD(2, 2), &wsa) == 0;
}

NetRuntime::~NetRuntime() {
    if (ok_) {
        WSACleanup();
    }
}

Net::Net(NetHandler& handler, const sockaddr_in& addr) : handler_(handler), addr_(addr) {}

Net::~Net() {
    if (port_ != nullptr) {
        CloseHandle(port_);
    }
}

bool Net::init() {
    port_ = CreateIoCompletionPort(INVALID_HANDLE_VALUE, nullptr, 0, 1);
    if (port_ == nullptr) {
        return false;
    }
    // ConnectEx is an extension function: its address comes from a socket of the same provider.
    const SOCKET s = WSASocketW(AF_INET, SOCK_STREAM, IPPROTO_TCP, nullptr, 0, WSA_FLAG_OVERLAPPED);
    if (s == INVALID_SOCKET) {
        return false;
    }
    GUID guid = WSAID_CONNECTEX;
    DWORD bytes = 0;
    const int rc = WSAIoctl(s, SIO_GET_EXTENSION_FUNCTION_POINTER, &guid, sizeof guid, &connect_ex_,
                            sizeof connect_ex_, &bytes, nullptr, nullptr);
    closesocket(s);
    return rc == 0 && connect_ex_ != nullptr;
}

void Net::connect(NetConn& c) {
    c.s = WSASocketW(AF_INET, SOCK_STREAM, IPPROTO_TCP, nullptr, 0, WSA_FLAG_OVERLAPPED);
    if (c.s == INVALID_SOCKET) {
        release(c, Cause::ConnectFailed);
        return;
    }
    const BOOL one = TRUE;
    setsockopt(c.s, IPPROTO_TCP, TCP_NODELAY, reinterpret_cast<const char*>(&one), sizeof one);
    // ConnectEx needs a bound socket.
    sockaddr_in any{};
    any.sin_family = AF_INET;
    any.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(c.s, reinterpret_cast<const sockaddr*>(&any), sizeof any) != 0 ||
        CreateIoCompletionPort(reinterpret_cast<HANDLE>(c.s), port_, 0, 0) == nullptr) {
        release(c, Cause::ConnectFailed);
        return;
    }
    std::memset(&c.connect_io.ov, 0, sizeof c.connect_io.ov);
    c.wleft = 0;
    DWORD sent = 0;
    if (!connect_ex_(c.s, reinterpret_cast<const sockaddr*>(&addr_), static_cast<int>(sizeof addr_), nullptr, 0,
                     &sent, &c.connect_io.ov) &&
        WSAGetLastError() != ERROR_IO_PENDING) {
        release(c, Cause::ConnectFailed);
        return;
    }
    c.connecting = true;  // a packet follows, also if ConnectEx finished at once
    ++c.pending;
    ++outstanding_;
}

void Net::post_recv(NetConn& c) {
    if (c.s == INVALID_SOCKET || c.recv_pending) {
        return;
    }
    WSABUF b{static_cast<ULONG>(c.rbuf.size()), c.rbuf.data()};
    DWORD n = 0;
    DWORD flags = 0;
    std::memset(&c.recv_io.ov, 0, sizeof c.recv_io.ov);
    if (WSARecv(c.s, &b, 1, &n, &flags, &c.recv_io.ov, nullptr) == SOCKET_ERROR &&
        WSAGetLastError() != WSA_IO_PENDING) {
        release(c, Cause::Reset);
        return;
    }
    c.recv_pending = true;
    ++c.pending;
    ++outstanding_;
}

void Net::post_send(NetConn& c) {
    WSABUF b{static_cast<ULONG>(c.wleft), const_cast<char*>(c.wptr)};
    DWORD n = 0;
    std::memset(&c.send_io.ov, 0, sizeof c.send_io.ov);
    if (WSASend(c.s, &b, 1, &n, 0, &c.send_io.ov, nullptr) == SOCKET_ERROR && WSAGetLastError() != WSA_IO_PENDING) {
        release(c, Cause::Reset);
        return;
    }
    c.send_pending = true;
    ++c.pending;
    ++outstanding_;
}

void Net::send(NetConn& c, const char* p, std::size_t n) {
    if (c.s == INVALID_SOCKET || c.connecting || c.send_pending) {
        release(c, Cause::Reset);  // not a connection to send on: cannot happen at depth 1
        return;
    }
    c.wptr = p;
    c.wleft = n;
    post_send(c);
}

void Net::close(NetConn& c) {
    if (c.s != INVALID_SOCKET) {
        release(c, Cause::Requested);
    }
}

// Closes the socket now; the operations in flight then complete with an error. closed() is
// reported by report_closed once none is left.
void Net::release(NetConn& c, Cause why) {
    if (c.s != INVALID_SOCKET) {
        closesocket(c.s);
        c.s = INVALID_SOCKET;
    }
    c.wleft = 0;
    if (!c.queued) {
        c.queued = true;
        c.cause = why;
        released_.push_back(&c);
    }
}

void Net::report_closed() {
    for (std::size_t i = 0; i < released_.size();) {
        NetConn* c = released_[i];
        if (c->pending != 0) {
            ++i;
            continue;
        }
        released_[i] = released_.back();
        released_.pop_back();
        c->queued = false;
        handler_.closed(*c, c->cause);
    }
}

// One completion. deliver false: only the bookkeeping, no callback and nothing new started.
void Net::complete(const OVERLAPPED_ENTRY& e, bool deliver) {
    if (e.lpOverlapped == nullptr) {
        return;
    }
    Io& io = *reinterpret_cast<Io*>(e.lpOverlapped);
    NetConn& c = *io.owner;
    --c.pending;
    --outstanding_;
    const bool success = e.lpOverlapped->Internal == 0;  // the operation's NTSTATUS: STATUS_SUCCESS
    const DWORD bytes = e.dwNumberOfBytesTransferred;
    switch (io.op) {
        case IoOp::Connect:
            c.connecting = false;
            if (!deliver || c.s == INVALID_SOCKET) {
                return;
            }
            if (!success) {
                release(c, Cause::ConnectFailed);
                return;
            }
            setsockopt(c.s, SOL_SOCKET, SO_UPDATE_CONNECT_CONTEXT, nullptr, 0);
            post_recv(c);
            if (c.s != INVALID_SOCKET) {
                handler_.connected(c);
            }
            return;
        case IoOp::Recv:
            c.recv_pending = false;
            if (!deliver || c.s == INVALID_SOCKET) {
                return;
            }
            if (!success) {
                release(c, Cause::Reset);
            } else if (bytes == 0) {
                release(c, Cause::PeerClosed);
            } else {
                handler_.data(c, c.rbuf.data(), bytes);
                post_recv(c);
            }
            return;
        case IoOp::Send:
            c.send_pending = false;
            if (!deliver || c.s == INVALID_SOCKET) {
                return;
            }
            if (!success || bytes > c.wleft) {
                release(c, Cause::Reset);
                return;
            }
            c.wptr += bytes;
            c.wleft -= bytes;
            if (c.wleft > 0) {
                post_send(c);  // a partial send: the rest
            }
            return;
    }
}

void Net::poll(int wait_ms) {
    std::array<OVERLAPPED_ENTRY, kMaxEntries> entries{};
    ULONG n = 0;
    if (!GetQueuedCompletionStatusEx(port_, entries.data(), kMaxEntries, &n, static_cast<DWORD>(wait_ms), FALSE)) {
        n = 0;
        if (GetLastError() != WAIT_TIMEOUT) {
            ok_ = false;
        }
    }
    const bool deliver = handler_.begin_batch();
    for (ULONG i = 0; i < n; ++i) {
        complete(entries[i], deliver);
    }
    if (deliver) {
        report_closed();
    }
}

bool Net::drain(int wait_ms) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(wait_ms);
    std::array<OVERLAPPED_ENTRY, kMaxEntries> entries{};
    while (outstanding_ > 0 && std::chrono::steady_clock::now() < deadline) {
        ULONG n = 0;
        if (!GetQueuedCompletionStatusEx(port_, entries.data(), kMaxEntries, &n, kDrainStepMs, FALSE)) {
            continue;
        }
        for (ULONG i = 0; i < n; ++i) {
            complete(entries[i], false);
        }
    }
    return outstanding_ == 0;
}

}  // namespace p2gen
