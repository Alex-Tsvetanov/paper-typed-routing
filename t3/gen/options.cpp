#include "options.hpp"

#include <cerrno>
#include <charconv>
#include <cmath>
#include <cstdlib>
#include <string_view>
#include <system_error>
#include <utility>

namespace p2gen {

namespace {

#if defined(_WIN32)
// SetThreadAffinityMask takes a mask of one processor group: 64 CPUs.
constexpr long long kMaxCpu = 63;
#else
constexpr long long kMaxCpu = 1023;  // glibc's CPU_SETSIZE - 1
#endif

constexpr long long kMaxCount = 1'000'000'000'000LL;

bool parse_int(std::string_view s, long long lo, long long hi, long long& out) {
    long long v = 0;
    const char* end = s.data() + s.size();
    const auto r = std::from_chars(s.data(), end, v);
    if (s.empty() || r.ec != std::errc{} || r.ptr != end || v < lo || v > hi) {
        return false;
    }
    out = v;
    return true;
}

// strtod rather than from_chars: floating-point from_chars is not in every standard library the
// sanitizer builds use.
bool parse_double(const std::string& s, double lo, double hi, double& out) {
    if (s.empty()) {
        return false;
    }
    char* end = nullptr;
    errno = 0;
    const double v = std::strtod(s.c_str(), &end);
    if (errno != 0 || end != s.c_str() + s.size() || !std::isfinite(v) || v < lo || v > hi) {
        return false;
    }
    out = v;
    return true;
}

bool parse_cpus(const std::string& s, std::vector<int>& out) {
    std::vector<int> cpus;
    std::size_t start = 0;
    for (;;) {
        const std::size_t comma = s.find(',', start);
        const std::string_view token(s.data() + start, (comma == std::string::npos ? s.size() : comma) - start);
        long long v = 0;
        if (!parse_int(token, 0, kMaxCpu, v)) {
            return false;
        }
        cpus.push_back(static_cast<int>(v));
        if (comma == std::string::npos) {
            break;
        }
        start = comma + 1;
    }
    out = std::move(cpus);
    return true;
}

}  // namespace

const char* usage_text() noexcept {
    return "usage: p2gen --port P --paths FILE [options]\n"
           "  --host A          IPv4 literal (default 127.0.0.1)\n"
           "  --port P          the server's port (required)\n"
           "  --paths FILE      request targets, one per line (required); connection i of C starts at\n"
           "                    target i*n/C of n and walks the file cyclically\n"
           "  --connections C   keep-alive connections, one request in flight on each (default 16)\n"
           "  --threads T       worker threads (default 1; at most C)\n"
           "  --cpus LIST       comma list of CPUs; thread k is pinned to the k-th (cyclically)\n"
           "  --warmup S        seconds before the measured window (default 1)\n"
           "  --duration S      measured window in seconds (default 5)\n"
           "  --timeout-ms N    stall limit of a connection with a request in flight (default 1000)\n"
           "  --out FILE        the JSON line also goes to this file\n"
           "  --count N         functional mode: exactly N requests, then counts only; no time is\n"
           "                    read for any output and none is printed (--warmup and --duration\n"
           "                    are accepted and ignored)\n"
           "exit codes: 0 success, 1 the run failed its own checks, 2 a bad command line\n";
}

ParsedOptions parse_options(const std::vector<std::string>& args) {
    ParsedOptions r;
    Options& o = r.opts;
    for (std::size_t i = 0; i < args.size(); i += 2) {
        const std::string& a = args[i];
        if (a == "--help" || a == "-h") {
            o.help = true;
            return r;
        }
        if (i + 1 >= args.size()) {
            r.error = "missing value for " + a;
            return r;
        }
        const std::string& v = args[i + 1];
        long long l = 0;
        bool ok = true;
        if (a == "--host") {
            o.host = v;
        } else if (a == "--paths") {
            o.paths = v;
        } else if (a == "--out") {
            o.out = v;
        } else if (a == "--cpus") {
            ok = parse_cpus(v, o.cpus);
            o.cpus_text = v;
        } else if (a == "--port") {
            ok = parse_int(v, 1, 65535, l);
            o.port = static_cast<int>(l);
        } else if (a == "--threads") {
            ok = parse_int(v, 1, 1024, l);
            o.threads = static_cast<int>(l);
        } else if (a == "--connections") {
            ok = parse_int(v, 1, 1'000'000, l);
            o.connections = static_cast<int>(l);
        } else if (a == "--timeout-ms") {
            ok = parse_int(v, 1, 600'000, l);
            o.timeout_ms = static_cast<int>(l);
        } else if (a == "--count") {
            ok = parse_int(v, 1, kMaxCount, l);
            o.count = static_cast<std::uint64_t>(l);
        } else if (a == "--warmup") {
            ok = parse_double(v, 0.0, 3600.0, o.warmup_s);
        } else if (a == "--duration") {
            ok = parse_double(v, 0.01, 3600.0, o.duration_s);
        } else {
            r.error = "unknown option: " + a;
            return r;
        }
        if (!ok) {
            r.error = "invalid value for " + a + ": " + v;
            return r;
        }
    }
    if (o.port == 0) {
        r.error = "--port is required";
    } else if (o.paths.empty()) {
        r.error = "--paths is required";
    } else if (o.threads > o.connections) {
        o.threads = o.connections;  // a thread without a connection has nothing to do
    }
    return r;
}

}  // namespace p2gen
