// The minimal server binary against lab/t1's contract (t1.py: start_server, wait_ready, probe,
// stop_process) and its command line (design/round2/minimal-server.md, sections 1 and 5):
// readiness when the listening socket accepts, GET / answered with the 13-byte body, the routes
// file's routes answered, SIGTERM exiting with 0, and --workers other than 1 refused. For each
// router arm built. No test framework.
//     test_contract SERVER_BINARY
#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

namespace {

int g_failures = 0;

#define CHECK(cond)                                                                   \
    do {                                                                              \
        if (!(cond)) {                                                                \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
            ++g_failures;                                                             \
        }                                                                             \
    } while (0)

std::uint16_t free_port() {
    const int fd = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    bind(fd, reinterpret_cast<sockaddr*>(&a), sizeof a);
    socklen_t len = sizeof a;
    getsockname(fd, reinterpret_cast<sockaddr*>(&a), &len);
    close(fd);
    return ntohs(a.sin_port);
}

int try_connect(std::uint16_t port) {
    const int fd = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_port = htons(port);
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(fd, reinterpret_cast<sockaddr*>(&a), sizeof a) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

// One request on a new connection, with Connection: close added: the whole response, until the
// server closes, up to `want` bytes or 2 s.
std::string request(std::uint16_t port, std::string raw, std::size_t want) {
    const int fd = try_connect(port);
    if (fd < 0) {
        return {};
    }
    raw.insert(raw.size() - 2, "Connection: close\r\n");
    send(fd, raw.data(), raw.size(), MSG_NOSIGNAL);
    std::string got;
    const auto until = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (got.size() < want && std::chrono::steady_clock::now() < until) {
        pollfd p{fd, POLLIN, 0};
        if (poll(&p, 1, 100) <= 0) {
            continue;
        }
        char buf[4096];
        const ssize_t n = recv(fd, buf, sizeof buf, 0);
        if (n <= 0) {
            break;
        }
        got.append(buf, static_cast<std::size_t>(n));
    }
    close(fd);
    return got;
}

pid_t start(const std::string& bin, const std::vector<std::string>& args) {
    const pid_t pid = fork();
    if (pid == 0) {
        std::vector<char*> argv{const_cast<char*>(bin.c_str())};
        for (const std::string& a : args) {
            argv.push_back(const_cast<char*>(a.c_str()));
        }
        argv.push_back(nullptr);
        execv(bin.c_str(), argv.data());
        _exit(127);
    }
    return pid;
}

// The exit status of pid within 5 s, or -1.
int wait_exit(pid_t pid) {
    const auto until = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (std::chrono::steady_clock::now() < until) {
        int st = 0;
        if (waitpid(pid, &st, WNOHANG) == pid) {
            return WIFEXITED(st) ? WEXITSTATUS(st) : 128 + WTERMSIG(st);
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    kill(pid, SIGKILL);
    waitpid(pid, nullptr, 0);
    return -1;
}

void test_arm(const std::string& bin, const std::string& routes, const std::string& arm) {
    const std::uint16_t port = free_port();
    const pid_t pid = start(bin, {"--port", std::to_string(port), "--workers", "1", "--routes", routes, "--router", arm});
    // Readiness: the listening socket accepts.
    bool ready = false;
    for (int i = 0; i < 250 && !ready; ++i) {
        const int fd = try_connect(port);
        if (fd >= 0) {
            close(fd);
            ready = true;
        } else {
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
    }
    CHECK(ready);
    const std::string body = "\r\n\r\nHello, World!";
    const auto ok = [&](const std::string& got) { return got.rfind("HTTP/1.1 200 OK\r\n", 0) == 0 && got.ends_with(body); };
    CHECK(ok(request(port, "GET / HTTP/1.1\r\nHost: t\r\n\r\n", 200)));
    CHECK(ok(request(port, "GET /users/42 HTTP/1.1\r\n\r\n", 200)));
    CHECK(ok(request(port, "GET /files/a/b/c HTTP/1.1\r\n\r\n", 200)));
    if (arm != "null") {
        CHECK(request(port, "GET /nothing/here/at/all HTTP/1.1\r\n\r\n", 200).rfind("HTTP/1.1 404 Not Found\r\n", 0) == 0);
    }
    CHECK(kill(pid, SIGTERM) == 0);
    CHECK(wait_exit(pid) == 0);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: test_contract SERVER_BINARY\n");
        return 2;
    }
    const std::string bin = argv[1];
    char dir[] = "/tmp/mserver-contract-XXXXXX";
    const std::string routes = std::string(mkdtemp(dir)) + "/routes.txt";
    std::ofstream(routes) << "GET /users/{id}\nGET /users/{id}/posts\nGET /files/{*path}\n";
    test_arm(bin, routes, "v2");
    test_arm(bin, routes, "v1");
    test_arm(bin, routes, "null");
    // More than one worker is refused at start.
    const pid_t two = start(bin, {"--port", std::to_string(free_port()), "--workers", "2", "--routes", routes, "--router", "v2"});
    CHECK(wait_exit(two) != 0);
    // A bad routes file is refused at start.
    const std::string bad = std::string(dir) + "/bad.txt";
    std::ofstream(bad) << "POST /x\n";
    CHECK(wait_exit(start(bin, {"--port", std::to_string(free_port()), "--workers", "1", "--routes", bad, "--router", "v2"})) != 0);
    std::remove(routes.c_str());
    std::remove(bad.c_str());
    rmdir(dir);
    if (g_failures == 0) {
        std::printf("test_contract: all checks passed\n");
    }
    return g_failures == 0 ? 0 : 1;
}
