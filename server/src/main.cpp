// The paper's minimal HTTP/1.1 server (design/round2/minimal-server.md; round 3:
// design/round3/end-to-end.md, sections 5 to 7):
//     mserver --port P --workers 1 --routes FILE --router NAME [--check]
// NAME is v2, v1 (Linux builds), null, or one of the external arms this build has (run with
// --router '?' for the list). It is ready when its listening socket (127.0.0.1:P) accepts. SIGTERM
// or SIGINT on Linux, Ctrl-C or Ctrl-Break on Windows (a child started in its own process group,
// as check_server.py starts it, gets Ctrl-Break only), stops it, and it exits with 0. Exit codes:
// 2 a bad command line, 3 the router refuses the routes, 1 any other failure. One worker only: any
// other count is refused at start.
#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <winsock2.h>
#include <windows.h>
#else
#include <pthread.h>
#include <signal.h>
#include <sys/eventfd.h>
#include <unistd.h>
#endif

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <exception>
#include <string>
#include <string_view>
#include <thread>

#include "arms.hpp"
#include "external.hpp"
#include "loop.hpp"

namespace {

int usage(const char* why) {
    std::fprintf(stderr, "mserver: %s\nusage: mserver --port P --workers 1 --routes FILE --router NAME [--check]\n",
                 why);
    return 2;
}

void list_arms() {
    std::fprintf(stderr, "router arms: v2%s null", MSERVER_WITH_V1 ? " v1" : "");
    for (const mserver::ExternalArm& e : mserver::external_arms()) {
        std::fprintf(stderr, " %s", e.name.c_str());
    }
    std::fprintf(stderr, "\n");
}

#if defined(_WIN32)

std::atomic<std::uintptr_t> g_port{0};

BOOL WINAPI on_console(DWORD event) {
    if (event == CTRL_C_EVENT || event == CTRL_BREAK_EVENT || event == CTRL_CLOSE_EVENT) {
        if (const std::uintptr_t port = g_port.load()) {
            mserver::post_stop(port);
        }
        return TRUE;
    }
    return FALSE;
}

int run(std::uint16_t port, const mserver::Router& router, bool check) {
    WSADATA wsa{};
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        std::fprintf(stderr, "mserver: WSAStartup failed\n");
        return 1;
    }
    int rc = 0;
    try {
        const std::uintptr_t iocp = mserver::make_port();
        g_port.store(iocp);
        SetConsoleCtrlHandler(on_console, TRUE);
        const mserver::Listener l = mserver::listen_loopback(port);
        try {
            mserver::serve(l, iocp, router, check);
        } catch (const std::exception& e) {
            std::fprintf(stderr, "mserver: %s\n", e.what());
            rc = 1;
        }
        closesocket(static_cast<SOCKET>(l.socket));
    } catch (const std::exception& e) {
        std::fprintf(stderr, "mserver: %s\n", e.what());
        rc = 1;
    }
    WSACleanup();
    return rc;
}

#else

int run(std::uint16_t port, const mserver::Router& router, bool check) {
    // SIGTERM and SIGINT go to one thread, which wakes the loop through an eventfd.
    sigset_t stop_signals;
    sigemptyset(&stop_signals);
    sigaddset(&stop_signals, SIGTERM);
    sigaddset(&stop_signals, SIGINT);
    pthread_sigmask(SIG_BLOCK, &stop_signals, nullptr);
    signal(SIGPIPE, SIG_IGN);
    const int stop = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
    if (stop < 0) {
        std::perror("mserver: eventfd");
        return 1;
    }
    std::thread signals([&] {
        int sig = 0;
        sigwait(&stop_signals, &sig);
        const std::uint64_t one = 1;
        [[maybe_unused]] const ssize_t n = write(stop, &one, sizeof one);
    });

    int rc = 0;
    try {
        const mserver::Listener l = mserver::listen_loopback(port);
        try {
            mserver::serve(l.fd, stop, router, check);
        } catch (const std::exception& e) {
            std::fprintf(stderr, "mserver: %s\n", e.what());
            rc = 1;
        }
        close(l.fd);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "mserver: %s\n", e.what());
        rc = 1;
    }
    if (rc != 0) {
        pthread_kill(signals.native_handle(), SIGTERM);  // wake the signal thread
    }
    signals.join();
    close(stop);
    return rc;
}

#endif

}  // namespace

int main(int argc, char** argv) {
    std::string port_text, workers = "1", routes_path, router_name;
    bool check = false;
    for (int i = 1; i < argc; ++i) {
        const std::string_view a = argv[i];
        if (a == "--check") {
            check = true;
            continue;
        }
        if (i + 1 >= argc) {
            return usage("an option without its value");
        }
        const std::string v = argv[++i];
        if (a == "--port") {
            port_text = v;
        } else if (a == "--workers") {
            workers = v;
        } else if (a == "--routes") {
            routes_path = v;
        } else if (a == "--router") {
            router_name = v;
        } else {
            return usage("an unknown option");
        }
    }
    if (router_name == "?") {
        list_arms();
        return 0;
    }
    if (workers != "1") {
        return usage("one worker only (--workers 1)");
    }
    if (port_text.empty() || routes_path.empty() || router_name.empty()) {
        return usage("--port, --routes and --router are required");
    }
    try {
        const unsigned long port = std::stoul(port_text);
        if (port > 65535) {
            return usage("a port above 65535");
        }
        const mserver::Arm arm = mserver::make_arm(router_name, mserver::read_routes(routes_path));
        return run(static_cast<std::uint16_t>(port), arm.router, check);
    } catch (const mserver::RefusedTable& e) {
        std::fprintf(stderr, "mserver: %s\n", e.what());
        return 3;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "mserver: %s\n", e.what());
        return 1;
    }
}
