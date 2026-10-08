// The minimal server's I/O (design/round2/minimal-server.md, section 3): one thread, epoll,
// level-triggered, a buffer in and a buffer out per connection, reused.
#pragma once

#include <cstddef>
#include <cstdint>

#include "route.hpp"

namespace mserver {

// The most a connection buffers of one request (its head and a body that is skipped); a request
// that does not fit is refused with 413 and the connection closes.
inline constexpr std::size_t kConnBuffer = 65536;

struct Listener {
    int fd = -1;
    std::uint16_t port = 0;
};

// A non-blocking listening TCP socket on 127.0.0.1; port 0 takes a free one. Throws
// std::system_error.
Listener listen_loopback(std::uint16_t port);

// Serves every connection of the listener with the calling thread until stop_fd (an eventfd)
// becomes readable, then closes every connection and returns. Throws std::system_error when it
// cannot set up.
void serve(int listen_fd, int stop_fd, const Router& router);

}  // namespace mserver
