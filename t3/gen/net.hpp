// The network backend of this system (net_common.hpp has the contract), and the few system calls
// the worker and main need beside it.
#pragma once

#include <string>

#if defined(_WIN32)
#include "net_iocp.hpp"
#else
#include "net_epoll.hpp"
#endif

namespace p2gen {

// Fills out with host (an IPv4 literal) and port. False if host is not one.
bool make_address(const std::string& host, int port, sockaddr_in& out);

// Pins the calling thread to one CPU. False if the system refuses.
bool pin_current_thread(int cpu);

// What the process needs before it opens a socket: WSAStartup on Windows; on Linux the descriptor
// limit raised to its hard maximum, as t1gen does.
class NetRuntime {
public:
    NetRuntime();
    ~NetRuntime();
    NetRuntime(const NetRuntime&) = delete;
    NetRuntime& operator=(const NetRuntime&) = delete;
    bool ok() const noexcept { return ok_; }

private:
    bool ok_ = true;
};

}  // namespace p2gen
