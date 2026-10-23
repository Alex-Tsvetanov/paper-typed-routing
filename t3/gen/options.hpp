// The command line of p2gen. Pure code: parse_options checks every value and every combination
// before anything touches the network or a file, so a bad command line (exit code 2) never costs
// a connection.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace p2gen {

struct Options {
    std::string host = "127.0.0.1";  // an IPv4 literal
    int port = 0;
    std::string paths;               // the file of request targets, one per line
    int threads = 1;
    int connections = 16;
    double warmup_s = 1.0;
    double duration_s = 5.0;
    int timeout_ms = 1000;
    std::string cpus_text;           // as given
    std::vector<int> cpus;           // thread k is pinned to cpus[k % size]; a timed run needs
                                     // at least `threads` distinct entries
    std::string out;                 // the file that also gets the JSON line
    std::uint64_t count = 0;         // > 0: count mode, exactly this many requests
    bool help = false;

    bool counting() const noexcept { return count != 0; }
};

struct ParsedOptions {
    Options opts;
    std::string error;  // empty when the command line is good
};

// args are the arguments after the program name.
ParsedOptions parse_options(const std::vector<std::string>& args);

const char* usage_text() noexcept;

}  // namespace p2gen
