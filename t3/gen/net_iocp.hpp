// The Windows backend of p2gen: one I/O completion port per thread, overlapped ConnectEx, WSARecv
// and WSASend, in the patterns of server/src/loop_iocp.cpp. Completions are turned into the
// handler's callbacks (net_common.hpp).
//
//   - Each connection has one WSARecv posted whenever it is open, so a close or a reset shows at
//     once, and at most one WSASend in flight (the generator has one request in flight).
//   - Sockets do not use FILE_SKIP_COMPLETION_PORT_ON_SUCCESS: every operation, one that finishes
//     at once too, delivers a packet. One path, so every completion is handled the same way.
//   - A connection the handler closes, or that fails, has its socket closed at once; its operations
//     then complete with an error, and those completions only clear its bookkeeping. closed() is
//     reported when none is left, and only then may the connection be used again.
//   - Memory under an operation is never freed while the operation is outstanding: drain() waits
//     for them, and the caller leaks what it cannot end (as server/src/loop_iocp.cpp does).
#pragma once

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#include <winsock2.h>
#include <mswsock.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <array>
#include <vector>

#include "net_common.hpp"

namespace p2gen {

enum class IoOp : std::uint8_t { Connect, Recv, Send };

struct Io {
    OVERLAPPED ov{};  // first, so a completion's pointer is the Io's
    NetConn* owner = nullptr;
    IoOp op = IoOp::Recv;
};

inline constexpr std::size_t kRecvBuffer = 16384;

struct NetConn {
    NetConn() {
        connect_io.owner = recv_io.owner = send_io.owner = this;
        connect_io.op = IoOp::Connect;
        recv_io.op = IoOp::Recv;
        send_io.op = IoOp::Send;
    }
    NetConn(const NetConn&) = delete;
    NetConn& operator=(const NetConn&) = delete;

    SOCKET s = INVALID_SOCKET;
    Io connect_io;
    Io recv_io;
    Io send_io;
    int pending = 0;           // operations posted whose completion has not been taken
    bool connecting = false;   // from ConnectEx until its completion is taken
    bool recv_pending = false;
    bool send_pending = false;
    bool queued = false;       // released, its closed() not yet reported
    Cause cause = Cause::Requested;
    const char* wptr = nullptr;  // the part of the request not yet sent
    std::size_t wleft = 0;
    std::array<char, kRecvBuffer> rbuf{};
};

class Net {
public:
    Net(NetHandler& handler, const sockaddr_in& addr);
    ~Net();
    Net(const Net&) = delete;
    Net& operator=(const Net&) = delete;

    bool init();
    // False once waiting on the port has failed for a reason other than a timeout.
    bool ok() const noexcept { return ok_; }

    void connect(NetConn& c);
    // [p, p + n) must stay valid until the request is answered or the connection is closed.
    void send(NetConn& c, const char* p, std::size_t n);
    void close(NetConn& c);

    // Waits up to wait_ms for completions and reports them.
    void poll(int wait_ms);

    // After every connection was closed: takes the completions of the operations still
    // outstanding, for at most wait_ms. True if none is left.
    bool drain(int wait_ms);

private:
    void release(NetConn& c, Cause why);
    void complete(const OVERLAPPED_ENTRY& e, bool deliver);
    void post_recv(NetConn& c);
    void post_send(NetConn& c);
    void report_closed();

    NetHandler& handler_;
    sockaddr_in addr_;
    HANDLE port_ = nullptr;
    LPFN_CONNECTEX connect_ex_ = nullptr;
    std::size_t outstanding_ = 0;  // operations posted, completions not yet taken
    std::vector<NetConn*> released_;
    bool ok_ = true;
};

}  // namespace p2gen
