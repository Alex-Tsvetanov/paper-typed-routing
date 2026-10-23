// The Linux backend of p2gen: one epoll instance per thread, level-triggered, non-blocking
// sockets, as lab/t1's t1gen. Readiness is turned into the handler's callbacks (net_common.hpp):
// a readable socket is read at once, and a request that does not go out whole stays in the
// connection until the socket is writable.
#pragma once

#include <netinet/in.h>

#include <vector>

#include "net_common.hpp"

namespace p2gen {

struct NetConn {
    int fd = -1;
    bool connecting = false;
    bool want_out = false;  // EPOLLOUT is registered
    bool queued = false;    // released, its closed() not yet reported
    Cause cause = Cause::Requested;
    const char* wptr = nullptr;  // the part of the request not yet written
    std::size_t wleft = 0;
};

class Net {
public:
    Net(NetHandler& handler, const sockaddr_in& addr);
    ~Net();
    Net(const Net&) = delete;
    Net& operator=(const Net&) = delete;

    bool init();
    bool ok() const noexcept { return true; }

    void connect(NetConn& c);
    // [p, p + n) must stay valid until the request is answered or the connection is closed.
    void send(NetConn& c, const char* p, std::size_t n);
    void close(NetConn& c);

    // Waits up to wait_ms for events and reports them.
    void poll(int wait_ms);

    // Ends the operations still outstanding after every connection was closed. Nothing is
    // outstanding with epoll.
    bool drain(int wait_ms);

private:
    void release(NetConn& c, Cause why);
    void dispatch(NetConn& c, std::uint32_t events);
    void finish_connect(NetConn& c);
    void read_ready(NetConn& c);
    void write_out(NetConn& c);
    void set_out(NetConn& c, bool out);
    void report_closed();

    NetHandler& handler_;
    sockaddr_in addr_;
    int ep_ = -1;
    std::vector<char> rbuf_;
    std::vector<NetConn*> released_;
};

}  // namespace p2gen
