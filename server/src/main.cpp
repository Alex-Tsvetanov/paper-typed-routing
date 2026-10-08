// The paper's minimal HTTP/1.1 server (design/round2/minimal-server.md):
//     mserver --port P --workers 1 --routes FILE --router v2|v1|null
// It is ready when its listening socket (127.0.0.1:P) accepts; SIGTERM or SIGINT stops it, and it
// exits with 0. One worker only: any other count is refused at start.
#include <pthread.h>
#include <signal.h>
#include <sys/eventfd.h>
#include <unistd.h>

#include <cstdint>
#include <cstdio>
#include <exception>
#include <string>
#include <string_view>
#include <thread>

#include "arms.hpp"
#include "loop.hpp"

namespace {

int usage(const char* why) {
    std::fprintf(stderr, "mserver: %s\nusage: mserver --port P --workers 1 --routes FILE --router v2|v1|null\n", why);
    return 2;
}

}  // namespace

int main(int argc, char** argv) {
    std::string port_text, workers = "1", routes_path, router_name;
    for (int i = 1; i < argc; ++i) {
        const std::string_view a = argv[i];
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

        const mserver::Listener l = mserver::listen_loopback(static_cast<std::uint16_t>(port));
        int rc = 0;
        try {
            mserver::serve(l.fd, stop, arm.router);
        } catch (const std::exception& e) {
            std::fprintf(stderr, "mserver: %s\n", e.what());
            rc = 1;
            pthread_kill(signals.native_handle(), SIGTERM);  // wake the signal thread
        }
        signals.join();
        close(l.fd);
        close(stop);
        return rc;
    } catch (const std::exception& e) {
        std::fprintf(stderr, "mserver: %s\n", e.what());
        return 1;
    }
}
