#include "net.hpp"

#include <arpa/inet.h>
#include <netinet/tcp.h>
#include <pthread.h>
#include <sched.h>
#include <sys/epoll.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <utility>

namespace p2gen {

namespace {
constexpr int kMaxEvents = 256;
constexpr std::size_t kReadBuffer = 65536;
}  // namespace

bool make_address(const std::string& host, int port, sockaddr_in& out) {
    out = sockaddr_in{};
    out.sin_family = AF_INET;
    out.sin_port = htons(static_cast<std::uint16_t>(port));
    return inet_pton(AF_INET, host.c_str(), &out.sin_addr) == 1;
}

bool pin_current_thread(int cpu) {
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    return pthread_setaffinity_np(pthread_self(), sizeof set, &set) == 0;
}

NetRuntime::NetRuntime() {
    rlimit rl{};
    if (getrlimit(RLIMIT_NOFILE, &rl) == 0 && rl.rlim_cur < rl.rlim_max) {
        rl.rlim_cur = rl.rlim_max;
        setrlimit(RLIMIT_NOFILE, &rl);
    }
}

NetRuntime::~NetRuntime() = default;

Net::Net(NetHandler& handler, const sockaddr_in& addr) : handler_(handler), addr_(addr), rbuf_(kReadBuffer) {}

Net::~Net() {
    if (ep_ >= 0) {
        ::close(ep_);
    }
}

bool Net::init() {
    ep_ = epoll_create1(EPOLL_CLOEXEC);
    return ep_ >= 0;
}

void Net::connect(NetConn& c) {
    const int fd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, IPPROTO_TCP);
    if (fd < 0) {
        release(c, Cause::ConnectFailed);
        return;
    }
    const int one = 1;
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    c.fd = fd;
    c.connecting = true;
    c.want_out = true;
    c.wleft = 0;
    if (::connect(fd, reinterpret_cast<const sockaddr*>(&addr_), sizeof addr_) != 0 && errno != EINPROGRESS) {
        release(c, Cause::ConnectFailed);
        return;
    }
    epoll_event ev{};
    ev.events = EPOLLOUT;
    ev.data.ptr = &c;
    if (epoll_ctl(ep_, EPOLL_CTL_ADD, fd, &ev) != 0) {
        release(c, Cause::ConnectFailed);
    }
}

void Net::send(NetConn& c, const char* p, std::size_t n) {
    if (c.fd < 0 || c.connecting || c.wleft != 0) {
        release(c, Cause::Reset);  // not a connection to send on: cannot happen at depth 1
        return;
    }
    c.wptr = p;
    c.wleft = n;
    write_out(c);
}

void Net::close(NetConn& c) {
    if (c.fd >= 0) {
        release(c, Cause::Requested);
    }
}

// Closes the socket now (epoll forgets a closed descriptor) and queues the report for the end of
// the next poll, so that no callback runs inside a call of the handler.
void Net::release(NetConn& c, Cause why) {
    if (c.fd >= 0) {
        ::close(c.fd);
        c.fd = -1;
    }
    c.connecting = false;
    c.want_out = false;
    c.wleft = 0;
    if (!c.queued) {
        c.queued = true;
        c.cause = why;
        released_.push_back(&c);
    }
}

void Net::report_closed() {
    std::vector<NetConn*> batch;
    batch.swap(released_);
    for (NetConn* c : batch) {
        c->queued = false;
        handler_.closed(*c, c->cause);
    }
}

void Net::poll(int wait_ms) {
    epoll_event evs[kMaxEvents];
    int n = epoll_wait(ep_, evs, kMaxEvents, wait_ms);
    if (n < 0) {
        n = 0;  // EINTR
    }
    if (!handler_.begin_batch()) {
        return;
    }
    for (int i = 0; i < n; ++i) {
        dispatch(*static_cast<NetConn*>(evs[i].data.ptr), evs[i].events);
    }
    report_closed();
}

void Net::dispatch(NetConn& c, std::uint32_t events) {
    if (c.fd < 0) {
        return;
    }
    if (c.connecting) {
        finish_connect(c);
        return;
    }
    if ((events & (EPOLLIN | EPOLLERR | EPOLLHUP)) != 0) {
        read_ready(c);  // recv tells an error or a close from data
        if (c.fd < 0) {
            return;
        }
    }
    if ((events & EPOLLOUT) != 0) {
        write_out(c);
    }
}

void Net::finish_connect(NetConn& c) {
    int err = 0;
    socklen_t len = sizeof err;
    if (getsockopt(c.fd, SOL_SOCKET, SO_ERROR, &err, &len) != 0 || err != 0) {
        release(c, Cause::ConnectFailed);
        return;
    }
    c.connecting = false;
    c.want_out = false;
    epoll_event ev{};
    ev.events = EPOLLIN;
    ev.data.ptr = &c;
    if (epoll_ctl(ep_, EPOLL_CTL_MOD, c.fd, &ev) != 0) {
        release(c, Cause::ConnectFailed);
        return;
    }
    handler_.connected(c);
}

void Net::read_ready(NetConn& c) {
    for (;;) {
        const ssize_t r = recv(c.fd, rbuf_.data(), rbuf_.size(), 0);
        if (r > 0) {
            handler_.data(c, rbuf_.data(), static_cast<std::size_t>(r));
            if (c.fd < 0 || static_cast<std::size_t>(r) < rbuf_.size()) {
                return;  // closed by the handler, or the socket is drained
            }
            continue;
        }
        if (r == 0) {
            release(c, Cause::PeerClosed);
            return;
        }
        if (errno == EINTR) {
            continue;
        }
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            return;
        }
        release(c, Cause::Reset);
        return;
    }
}

void Net::write_out(NetConn& c) {
    while (c.wleft > 0) {
        const ssize_t w = ::send(c.fd, c.wptr, c.wleft, MSG_NOSIGNAL);
        if (w > 0) {
            c.wptr += w;
            c.wleft -= static_cast<std::size_t>(w);
            continue;
        }
        if (w < 0 && errno == EINTR) {
            continue;
        }
        if (w < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            set_out(c, true);
            return;
        }
        release(c, Cause::Reset);
        return;
    }
    set_out(c, false);
}

void Net::set_out(NetConn& c, bool out) {
    if (c.want_out == out) {
        return;
    }
    epoll_event ev{};
    ev.events = EPOLLIN | (out ? static_cast<std::uint32_t>(EPOLLOUT) : 0u);
    ev.data.ptr = &c;
    epoll_ctl(ep_, EPOLL_CTL_MOD, c.fd, &ev);
    c.want_out = out;
}

bool Net::drain(int) {
    return true;
}

}  // namespace p2gen
