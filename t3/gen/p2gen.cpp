// p2gen: the HTTP/1.1 load generator of P2's end-to-end block (design/round3/end-to-end.md,
// section 8). It does what lab/t1's t1gen does in its closed loop at depth 1, on Linux and on
// Windows, and no more:
//
//   - C keep-alive connections over T threads, each thread pinned to one CPU of --cpus, and one
//     request in flight on each connection. Connection i of C starts at target i * n / C of the n
//     targets of --paths and walks them cyclically, so every target is requested equally often.
//   - An answer completes a request only if it is 200 with the 13-byte body "Hello, World!";
//     anything else is an error, by kind (framing.hpp, report.hpp).
//   - Timed mode: a warm-up, then a window between two instants the main thread marks on stdout
//     (MEASURE_START, MEASURE_END, each with the steady clock in ns). Only answers completed in the
//     window count. One JSON line at the end, also to --out.
//   - Count mode (--count N): the functional mode of the development machine. Exactly N requests
//     over the connections, every answer checked, then counts only. It prints no time, no rate and
//     no latency, marks no window, and reads no clock for any output.
//
// Exit codes: 0 success, 1 a run that failed its own checks, 2 a bad command line.
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <exception>
#include <fstream>
#include <memory>
#include <string>
#include <thread>
#include <vector>

#include "net.hpp"
#include "options.hpp"
#include "report.hpp"
#include "requests.hpp"
#include "worker.hpp"

#ifndef P2GEN_COMMIT
#define P2GEN_COMMIT "unknown"
#endif

namespace {

using p2gen::Options;
using SteadyClock = std::chrono::steady_clock;

std::uint64_t to_ns(SteadyClock::time_point t) {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(t.time_since_epoch()).count());
}

SteadyClock::duration seconds(double s) {
    return std::chrono::duration_cast<SteadyClock::duration>(std::chrono::duration<double>(s));
}

// The warm-up, the window and its two marks. Returns the window's two instants.
void run_window(const Options& o, p2gen::Shared& shared, std::uint64_t& t0_ns, std::uint64_t& t1_ns) {
    const auto launch = SteadyClock::now();
    std::this_thread::sleep_until(launch + seconds(o.warmup_s));
    shared.phase.store(p2gen::kMeasure, std::memory_order_release);
    const auto t0 = SteadyClock::now();
    t0_ns = to_ns(t0);
    std::printf("MEASURE_START %llu\n", static_cast<unsigned long long>(t0_ns));
    std::fflush(stdout);

    std::this_thread::sleep_until(t0 + seconds(o.duration_s));
    t1_ns = to_ns(SteadyClock::now());
    shared.phase.store(p2gen::kStop, std::memory_order_release);
    std::printf("MEASURE_END %llu\n", static_cast<unsigned long long>(t1_ns));
    std::fflush(stdout);
}

int run(const Options& o, const p2gen::Requests& reqs, const sockaddr_in& addr, std::ofstream& out) {
    p2gen::Shared shared(o, reqs, addr);
    std::vector<std::unique_ptr<p2gen::Worker>> workers;
    int first = 0;
    for (int i = 0; i < o.threads; ++i) {
        const int n = o.connections / o.threads + (i < o.connections % o.threads ? 1 : 0);
        const int cpu = o.cpus.empty() ? -1 : o.cpus[static_cast<std::size_t>(i) % o.cpus.size()];
        workers.push_back(std::make_unique<p2gen::Worker>(i, cpu, first, n, shared));
        first += n;
    }

    std::vector<std::thread> threads;
    try {
        for (auto& w : workers) {
            threads.emplace_back([&w] { w->run(); });
        }
    } catch (const std::exception& e) {
        std::fprintf(stderr, "p2gen: cannot start a thread: %s\n", e.what());
        shared.abort.store(true);
        shared.phase.store(p2gen::kStop);
        for (auto& t : threads) {
            t.join();
        }
        return 1;
    }

    std::uint64_t t0_ns = 0;
    std::uint64_t t1_ns = 0;
    if (!o.counting()) {
        run_window(o, shared, t0_ns, t1_ns);
    }
    for (auto& t : threads) {
        t.join();
    }

    p2gen::Totals totals;
    for (const auto& w : workers) {
        totals.fold(w->stats());
    }
    const std::string commit = P2GEN_COMMIT;
    const std::string line = o.counting() ? p2gen::render_count(o, commit, totals)
                                          : p2gen::render_timed(o, commit, reqs.size(), reqs.get(0).size(), t0_ns,
                                                                t1_ns, totals);
    std::printf("%s\n", line.c_str());
    std::fflush(stdout);
    bool wrote = true;
    if (out.is_open()) {
        out << line << '\n';
        out.flush();
        wrote = static_cast<bool>(out);
        if (!wrote) {
            std::fprintf(stderr, "p2gen: cannot write %s\n", o.out.c_str());
        }
    }
    const bool ok = o.counting() ? p2gen::count_ok(o, totals) : p2gen::timed_ok(totals);
    return ok && wrote ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
    const std::vector<std::string> args(argv + 1, argv + argc);
    const p2gen::ParsedOptions parsed = p2gen::parse_options(args);
    if (!parsed.error.empty()) {
        std::fprintf(stderr, "p2gen: %s\n%s", parsed.error.c_str(), p2gen::usage_text());
        return 2;
    }
    const Options& o = parsed.opts;
    if (o.help) {
        std::fputs(p2gen::usage_text(), stderr);
        return 0;
    }

    // Everything that can make the command line bad is checked before the first connection.
    sockaddr_in addr{};
    if (!p2gen::make_address(o.host, o.port, addr)) {
        std::fprintf(stderr, "p2gen: --host must be an IPv4 literal\n");
        return 2;
    }
    std::string targets_text;
    p2gen::Requests reqs;
    std::string error = p2gen::read_file(o.paths, targets_text);
    if (error.empty()) {
        error = p2gen::build_requests(targets_text, o.host, o.port, reqs);
    }
    if (!error.empty()) {
        std::fprintf(stderr, "p2gen: --paths: %s\n", error.c_str());
        return 2;
    }
    std::ofstream out;
    if (!o.out.empty()) {
        out.open(o.out, std::ios::binary | std::ios::trunc);
        if (!out) {
            std::fprintf(stderr, "p2gen: cannot write --out %s\n", o.out.c_str());
            return 2;
        }
    }

    p2gen::NetRuntime runtime;
    if (!runtime.ok()) {
        std::fprintf(stderr, "p2gen: cannot start the network stack\n");
        return 1;
    }
    try {
        return run(o, reqs, addr, out);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "p2gen: %s\n", e.what());
        return 1;
    }
}
