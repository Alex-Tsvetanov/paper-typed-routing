// The minimal server's I/O: see loop.hpp.
#include "loop.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <array>
#include <cerrno>
#include <cstring>
#include <ctime>
#include <memory>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>

#include "http1.hpp"

namespace mserver {

namespace {

[[noreturn]] void fail(const char* what) {
    throw std::system_error(errno, std::generic_category(), what);
}

struct Conn {
    int fd = -1;
    std::vector<char> in = std::vector<char>(kConnBuffer);
    std::size_t in_len = 0;
    std::string out;
    std::size_t out_off = 0;
    bool closing = false;      // close once `out` is sent
    bool peer_closed = false;  // the peer sent its last byte
    std::uint32_t events = 0;  // what epoll watches
};

// epoll's data for the listener and for the stop eventfd; a connection's is its Conn*.
constexpr std::uint64_t kListenTag = 1;
constexpr std::uint64_t kStopTag = 2;

class Server {
public:
    Server(int listen_fd, int stop_fd, const Router& router)
        : listen_fd_(listen_fd), stop_fd_(stop_fd), router_(router) {
        ep_ = epoll_create1(EPOLL_CLOEXEC);
        if (ep_ < 0) {
            fail("epoll_create1");
        }
        watch(listen_fd_, EPOLLIN, kListenTag);
        watch(stop_fd_, EPOLLIN, kStopTag);
    }

    ~Server() {
        for (auto& c : conns_) {
            if (c->fd >= 0) {
                close(c->fd);
            }
        }
        close(ep_);
    }

    void run() {
        std::array<epoll_event, 64> events{};  // value-initialized: MemorySanitizer
        bool running = true;
        while (running) {
            refresh_date();
            const int n = epoll_wait(ep_, events.data(), static_cast<int>(events.size()), 1000);
            if (n < 0) {
                if (errno == EINTR) {
                    continue;
                }
                fail("epoll_wait");
            }
            for (int i = 0; i < n; ++i) {
                const std::uint64_t tag = events[i].data.u64;
                if (tag == kStopTag) {
                    running = false;
                } else if (tag == kListenTag) {
                    accept_all();
                } else {
                    Conn& c = *static_cast<Conn*>(events[i].data.ptr);
                    if (c.fd < 0) {
                        continue;  // closed earlier in this batch
                    }
                    if ((events[i].events & (EPOLLIN | EPOLLHUP | EPOLLERR)) != 0) {
                        on_readable(c);
                    }
                    if (c.fd >= 0 && (events[i].events & EPOLLOUT) != 0) {
                        flush(c);
                    }
                }
            }
            reap();  // a closed connection's Conn is freed only after its batch
        }
    }

private:
    int listen_fd_;
    int stop_fd_;
    Router router_;
    int ep_ = -1;
    Responses responses_;
    RouteResult scratch_;
    std::time_t date_second_ = -1;
    std::vector<std::unique_ptr<Conn>> conns_;

    void watch(int fd, std::uint32_t events, std::uint64_t tag) {
        epoll_event e{};
        e.events = events;
        e.data.u64 = tag;
        if (epoll_ctl(ep_, EPOLL_CTL_ADD, fd, &e) != 0) {
            fail("epoll_ctl");
        }
    }

    void set_events(Conn& c, std::uint32_t events) {
        if (c.events == events) {
            return;
        }
        epoll_event e{};
        e.events = events;
        e.data.ptr = &c;
        epoll_ctl(ep_, EPOLL_CTL_MOD, c.fd, &e);
        c.events = events;
    }

    void refresh_date() {
        const std::time_t now = std::time(nullptr);
        if (now == date_second_) {
            return;
        }
        date_second_ = now;
        std::tm tm{};
        gmtime_r(&now, &tm);
        char buf[32] = {};
        const std::size_t n = std::strftime(buf, sizeof buf, "%a, %d %b %Y %H:%M:%S GMT", &tm);
        responses_.set_date(std::string_view(buf, n));
    }

    void accept_all() {
        while (true) {
            const int fd = accept4(listen_fd_, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
            if (fd < 0) {
                return;  // EAGAIN: none left; any other error: try again at the next event
            }
            const int one = 1;
            setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
            auto c = std::make_unique<Conn>();
            c->fd = fd;
            c->out.reserve(4096);
            c->events = EPOLLIN;
            epoll_event e{};
            e.events = EPOLLIN;
            e.data.ptr = c.get();
            if (epoll_ctl(ep_, EPOLL_CTL_ADD, fd, &e) != 0) {
                close(fd);
                continue;
            }
            conns_.push_back(std::move(c));
        }
    }

    void on_readable(Conn& c) {
        while (c.in_len < kConnBuffer && !c.closing) {
            const ssize_t n = recv(c.fd, c.in.data() + c.in_len, kConnBuffer - c.in_len, 0);
            if (n > 0) {
                c.in_len += static_cast<std::size_t>(n);
                continue;
            }
            if (n == 0) {
                c.peer_closed = true;
                break;
            }
            if (errno == EINTR) {
                continue;
            }
            if (errno != EAGAIN && errno != EWOULDBLOCK) {
                drop(c);
                return;
            }
            break;
        }
        process(c);
        flush(c);
    }

    // Answers every complete request in the connection's buffer, in order.
    void process(Conn& c) {
        std::size_t off = 0;
        while (!c.closing && off < c.in_len) {
            const Parsed p = parse_request(std::string_view(c.in.data() + off, c.in_len - off));
            if (p.state == Parse::Complete) {
                responses_.answer(p.request, router_, scratch_, c.out);
                off += p.consumed;
                c.closing = !p.request.keep_alive;
            } else if (p.state == Parse::Refused) {
                responses_.refuse(p.refusal, c.out);
                c.closing = true;
            } else {
                if (off == 0 && c.in_len == kConnBuffer) {
                    responses_.refuse(413, c.out);  // a request larger than the buffer
                    c.closing = true;
                }
                break;
            }
        }
        if (off != 0) {
            std::memmove(c.in.data(), c.in.data() + off, c.in_len - off);
            c.in_len -= off;
        }
    }

    void flush(Conn& c) {
        while (c.out_off < c.out.size()) {
            const ssize_t n = send(c.fd, c.out.data() + c.out_off, c.out.size() - c.out_off, MSG_NOSIGNAL);
            if (n > 0) {
                c.out_off += static_cast<std::size_t>(n);
                continue;
            }
            if (n < 0 && errno == EINTR) {
                continue;
            }
            if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
                // The rest when the socket can take it; a closing connection reads no more.
                set_events(c, c.closing ? EPOLLOUT : (EPOLLIN | EPOLLOUT));
                return;
            }
            drop(c);
            return;
        }
        c.out.clear();
        c.out_off = 0;
        if (c.closing || c.peer_closed) {
            drop(c);
            return;
        }
        set_events(c, EPOLLIN);
    }

    void drop(Conn& c) {
        epoll_ctl(ep_, EPOLL_CTL_DEL, c.fd, nullptr);
        close(c.fd);
        c.fd = -1;
    }

    void reap() {
        for (std::size_t i = 0; i < conns_.size();) {
            if (conns_[i]->fd < 0) {
                conns_[i] = std::move(conns_.back());
                conns_.pop_back();
            } else {
                ++i;
            }
        }
    }
};

}  // namespace

Listener listen_loopback(std::uint16_t port) {
    const int fd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        fail("socket");
    }
    const int one = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_port = htons(port);
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) != 0 || listen(fd, 1024) != 0) {
        const int e = errno;
        close(fd);
        errno = e;
        fail("bind or listen");
    }
    socklen_t len = sizeof a;
    getsockname(fd, reinterpret_cast<sockaddr*>(&a), &len);
    return {fd, ntohs(a.sin_port)};
}

void serve(int listen_fd, int stop_fd, const Router& router) {
    Server s(listen_fd, stop_fd, router);
    s.run();
}

}  // namespace mserver
