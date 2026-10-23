// The minimal server's I/O (design/round2/minimal-server.md, section 3): one thread, a buffer in
// and a buffer out per connection, reused. On Linux epoll, level-triggered (loop.cpp). On Windows
// an I/O completion port with AcceptEx and overlapped WSARecv and WSASend (loop_iocp.cpp;
// design/round3/end-to-end.md, section 7). Both serve the same HTTP code (http1.hpp) and the same
// router interface (route.hpp).
#pragma once

#include <cstddef>
#include <cstdint>

#include "route.hpp"

namespace mserver {

// The most a connection buffers of one request (its head and a body that is skipped); a request
// that does not fit is refused with 413 and the connection closes.
inline constexpr std::size_t kConnBuffer = 65536;

#if defined(_WIN32)

struct Listener {
    std::uintptr_t socket = ~std::uintptr_t{0};  // a SOCKET
    std::uint16_t port = 0;
};

// A listening TCP socket on 127.0.0.1, opened for overlapped I/O; port 0 takes a free one. Needs
// WSAStartup first. Throws std::system_error.
Listener listen_loopback(std::uint16_t port);

// The completion port serve() waits on; post_stop() makes serve() return, from any thread (the
// console control handler included). Throws std::system_error.
std::uintptr_t make_port();
void post_stop(std::uintptr_t port) noexcept;

// Serves every connection of the listener with the calling thread until post_stop(port), then
// closes every connection, waits for their operations to end, and returns. check: the check mode of
// design/round3/end-to-end.md, section 5. Throws std::system_error when it cannot set up.
void serve(const Listener& listener, std::uintptr_t port, const Router& router, bool check = false);

#else

struct Listener {
    int fd = -1;
    std::uint16_t port = 0;
};

// A non-blocking listening TCP socket on 127.0.0.1; port 0 takes a free one. Throws
// std::system_error.
Listener listen_loopback(std::uint16_t port);

// Serves every connection of the listener with the calling thread until stop_fd (an eventfd)
// becomes readable, then closes every connection and returns. check: the check mode of
// design/round3/end-to-end.md, section 5. Throws std::system_error when it cannot set up.
void serve(int listen_fd, int stop_fd, const Router& router, bool check = false);

#endif

}  // namespace mserver
