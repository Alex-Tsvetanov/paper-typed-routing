// What the two network backends of p2gen share (design/round3/end-to-end.md, section 8): epoll on
// Linux (net_epoll.*), one I/O completion port per thread on Windows (net_iocp.*). A backend owns
// the sockets and the waiting. It reports to a NetHandler, the worker's logic, which is the same
// code on both systems.
//
// The contract, which keeps the handler free of the two systems' differences:
//   - Every callback comes from Net::poll, on the polling thread, never from inside a call the
//     handler made. So the handler may call connect, send and close from any callback.
//   - closed() is the only report of a lost connection, and it comes once per connection, after the
//     socket is released and no operation of it is outstanding. Until then the connection must not
//     be connected again. The cause is the first one seen: Requested if the handler closed it.
//   - send() has no result. If it fails, closed() follows with Reset.
#pragma once

#include <chrono>
#include <cstddef>
#include <cstdint>

namespace p2gen {

// The steady clock, in ns.
inline std::uint64_t clock_ns() noexcept {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch())
            .count());
}

enum class Cause : std::uint8_t {
    Requested,      // the handler closed the connection
    ConnectFailed,  // the connection attempt was refused or failed
    Reset,          // an open connection failed with a socket error
    PeerClosed      // the server closed an open connection
};

struct NetConn;  // the backend's state of one connection (net_epoll.hpp, net_iocp.hpp)

class NetHandler {
public:
    virtual ~NetHandler() = default;

    // Once per wait, as it returns and before its events are delivered. False ends the run: the
    // events of this wait are then dropped.
    virtual bool begin_batch() = 0;

    // The connection is up. The handler may send.
    virtual void connected(NetConn& c) = 0;

    // Bytes arrived. They are valid until this call returns.
    virtual void data(NetConn& c, const char* p, std::size_t n) = 0;

    virtual void closed(NetConn& c, Cause why) = 0;
};

}  // namespace p2gen
