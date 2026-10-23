// Unit tests of p2gen's pure code: the histogram and its percentiles on synthetic values, the answer
// parser (framing.hpp) on every chunking, the command line, the request builder, and the report
// (count mode's line must hold no time). No network, no clock, no file: nothing here is timed.
// No test framework.
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <string>
#include <string_view>
#include <vector>

#include "framing.hpp"
#include "histogram.hpp"
#include "options.hpp"
#include "report.hpp"
#include "requests.hpp"
#include "stats.hpp"

namespace {

int g_failures = 0;

#define CHECK(cond)                                                                       \
    do {                                                                                  \
        if (!(cond)) {                                                                    \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
            ++g_failures;                                                                 \
        }                                                                                 \
    } while (0)

using namespace p2gen;

// ---- histogram -----------------------------------------------------------------------------

void test_histogram_buckets() {
    // Exact below 256.
    for (std::uint64_t v = 0; v < 256; ++v) {
        CHECK(Histogram::index(v) == static_cast<int>(v));
        CHECK(Histogram::value(static_cast<int>(v)) == v);
    }
    // The first log bucket starts at 256 and is 2 wide; its midpoint is 257.
    CHECK(Histogram::index(256) == 256);
    CHECK(Histogram::index(257) == 256);
    CHECK(Histogram::index(258) == 257);
    CHECK(Histogram::value(256) == 257);
    // The last bucket holds the largest value.
    CHECK(Histogram::index(UINT64_MAX) == Histogram::kBuckets - 1);

    // Monotone, in range, and the midpoint is within 1/256 of the value, at every power of two
    // and next to it.
    int last = -1;
    for (int bit = 8; bit < 64; ++bit) {
        for (const std::int64_t d : {-1, 0, 1, 3}) {
            const std::uint64_t base = std::uint64_t{1} << bit;
            const std::uint64_t v = d < 0 ? base - 1 : base + static_cast<std::uint64_t>(d);
            const int idx = Histogram::index(v);
            CHECK(idx >= 0 && idx < Histogram::kBuckets);
            CHECK(idx >= last);
            last = idx;
            const std::uint64_t mid = Histogram::value(idx);
            const std::uint64_t err = mid > v ? mid - v : v - mid;
            CHECK(err <= v / 256 + 1);
        }
    }
    // The bucket of a value is the bucket of its midpoint.
    for (std::uint64_t v = 1; v < (std::uint64_t{1} << 40); v = v * 3 + 1) {
        CHECK(Histogram::index(Histogram::value(Histogram::index(v))) == Histogram::index(v));
    }
}

void test_histogram_quantiles() {
    Histogram empty;
    CHECK(empty.count() == 0);
    CHECK(empty.quantile(0.5) == 0);
    CHECK(empty.min() == 0 && empty.max() == 0);
    CHECK(empty.mean() == 0.0);

    // 1..100 are all exact buckets.
    Histogram h;
    for (std::uint64_t v = 1; v <= 100; ++v) {
        h.add(v);
    }
    CHECK(h.count() == 100);
    CHECK(h.quantile(0.0) == 1);
    CHECK(h.quantile(0.50) == 50);
    CHECK(h.quantile(0.90) == 90);
    CHECK(h.quantile(0.99) == 99);
    CHECK(h.quantile(0.999) == 100);
    CHECK(h.quantile(1.0) == 100);
    CHECK(h.min() == 1 && h.max() == 100);
    CHECK(h.mean() == 50.5);

    // 1..10000: within the bucket error.
    Histogram big;
    for (std::uint64_t v = 1; v <= 10000; ++v) {
        big.add(v);
    }
    const auto near = [](std::uint64_t got, std::uint64_t want) {
        const std::uint64_t err = got > want ? got - want : want - got;
        return err <= want / 256 + 1;
    };
    CHECK(near(big.quantile(0.50), 5000));
    CHECK(near(big.quantile(0.90), 9000));
    CHECK(near(big.quantile(0.99), 9900));
    CHECK(near(big.quantile(0.999), 9990));
    CHECK(big.max() == 10000);

    // One value: clamped to it exactly, whatever its bucket midpoint is.
    Histogram one;
    one.add(1000);
    for (const double q : {0.0, 0.5, 0.9, 0.99, 0.999, 1.0}) {
        CHECK(one.quantile(q) == 1000);
    }

    // An outlier moves max and nothing below p99.9.
    Histogram tail;
    for (int i = 0; i < 999; ++i) {
        tail.add(1000);
    }
    tail.add(1'000'000'000);
    CHECK(tail.quantile(0.999) >= 1000 && tail.quantile(0.999) <= 1003);  // the bucket of 1000
    CHECK(tail.quantile(1.0) == 1'000'000'000);
    CHECK(tail.max() == 1'000'000'000);

    // The largest value does not overflow anything.
    Histogram top;
    top.add(UINT64_MAX);
    CHECK(top.quantile(0.5) == UINT64_MAX);
}

void test_histogram_merge() {
    Histogram a;
    Histogram b;
    Histogram both;
    for (std::uint64_t v = 1; v <= 5000; ++v) {
        ((v % 3) == 0 ? a : b).add(v * 7);
        both.add(v * 7);
    }
    Histogram merged = a;
    merged.merge(b);
    CHECK(merged.count() == both.count());
    CHECK(merged.min() == both.min());
    CHECK(merged.max() == both.max());
    CHECK(merged.mean() == both.mean());
    for (const double q : {0.5, 0.9, 0.99, 0.999}) {
        CHECK(merged.quantile(q) == both.quantile(q));
    }
    // Merging into an empty one, and an empty one in.
    Histogram empty;
    empty.merge(a);
    CHECK(empty.min() == a.min() && empty.max() == a.max() && empty.count() == a.count());
    a.merge(Histogram{});
    CHECK(a.count() == empty.count());
}

// ---- answer framing ------------------------------------------------------------------------

constexpr std::string_view kOk = "HTTP/1.1 200 OK\r\ncontent-length: 13\r\n\r\nHello, World!";

struct Fed {
    Framer::State state = Framer::State::Head;
    std::size_t used = 0;
    bool early = false;  // Done or Bad before the last chunk
};

// Feeds text in chunks of the given size, as a socket may deliver it.
Fed feed_chunks(Framer& f, std::string_view text, std::size_t chunk) {
    Fed r;
    std::size_t pos = 0;
    while (pos < text.size()) {
        const std::size_t n = std::min(chunk, text.size() - pos);
        const std::size_t took = f.feed(text.data() + pos, n);
        r.used += took;
        pos += took;
        if (f.state() == Framer::State::Done || f.state() == Framer::State::Bad) {
            r.early = pos < text.size();
            break;
        }
    }
    r.state = f.state();
    return r;
}

void test_framer_good() {
    Framer f;
    Fed r = feed_chunks(f, kOk, kOk.size());
    CHECK(r.state == Framer::State::Done && r.used == kOk.size());
    CHECK(f.answer().status == 200 && f.answer().length == 13 && f.answer().body_ok && !f.answer().close);

    // The real server's head, and a mixed-case name.
    f.reset();
    const std::string_view real =
        "HTTP/1.1 200 OK\r\nDate: Fri, 23 Oct 2026 10:00:00 GMT\r\nContent-Type: text/plain\r\nContent-Length: "
        "13\r\n\r\nHello, World!";
    r = feed_chunks(f, real, real.size());
    CHECK(r.state == Framer::State::Done && f.answer().body_ok);
    f.reset();
    r = feed_chunks(f, "HTTP/1.1 200 OK\r\nCoNtEnT-LeNgTh:   13  \r\n\r\nHello, World!", 1000);
    CHECK(r.state == Framer::State::Done && f.answer().body_ok);

    // Every chunking: the answer ends only with its last byte.
    for (const std::string_view text : {kOk, real}) {
        for (std::size_t chunk = 1; chunk <= text.size(); ++chunk) {
            Framer g;
            const Fed s = feed_chunks(g, text, chunk);
            CHECK(s.state == Framer::State::Done);
            CHECK(!s.early);
            CHECK(s.used == text.size());
            CHECK(g.answer().status == 200 && g.answer().body_ok);
        }
    }
}

void test_framer_classes() {
    Framer f;
    // 404 with an empty body.
    Fed r = feed_chunks(f, "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n", 100);
    CHECK(r.state == Framer::State::Done && f.answer().status == 404 && !f.answer().body_ok);

    // 200 whose body is the wrong 13 bytes, the wrong length, or empty.
    for (const std::string_view text : {
             std::string_view("HTTP/1.1 200 OK\r\nContent-Length: 13\r\n\r\nHello, World?"),
             std::string_view("HTTP/1.1 200 OK\r\nContent-Length: 13\r\n\r\nhello, World!"),
             std::string_view("HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nHello"),
             std::string_view("HTTP/1.1 200 OK\r\nContent-Length: 14\r\n\r\nHello, World!\n"),
             std::string_view("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"),
         }) {
        f.reset();
        r = feed_chunks(f, text, 100);
        CHECK(r.state == Framer::State::Done && f.answer().status == 200 && !f.answer().body_ok);
        f.reset();
        r = feed_chunks(f, text, 1);
        CHECK(r.state == Framer::State::Done && f.answer().status == 200 && !f.answer().body_ok);
    }

    // The mismatch is in a later piece of the body.
    f.reset();
    constexpr std::string_view first_piece = "HTTP/1.1 200 OK\r\nContent-Length: 13\r\n\r\nHello, ";
    f.feed(first_piece.data(), first_piece.size());
    CHECK(f.state() == Framer::State::Body);
    f.feed("World?", 6);
    CHECK(f.state() == Framer::State::Done && !f.answer().body_ok);

    // A route's id as check mode answers: framed, and not the 13 bytes.
    f.reset();
    r = feed_chunks(f, "HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\n12\t\n", 100);
    CHECK(r.state == Framer::State::Done && !f.answer().body_ok);

    // Statuses without a body and without a length.
    f.reset();
    r = feed_chunks(f, "HTTP/1.1 204 No Content\r\n\r\n", 100);
    CHECK(r.state == Framer::State::Done && f.answer().status == 204 && f.answer().length == 0);
    f.reset();
    r = feed_chunks(f, "HTTP/1.1 304 Not Modified\r\n\r\n", 100);
    CHECK(r.state == Framer::State::Done && f.answer().status == 304);
}

void test_framer_extra_and_reuse() {
    Framer f;
    const std::string with_extra = std::string(kOk) + "X";
    const std::size_t took = f.feed(with_extra.data(), with_extra.size());
    CHECK(took == kOk.size());  // the stray byte is left to the caller
    CHECK(f.state() == Framer::State::Done);
    CHECK(f.feed("Y", 1) == 0);  // nothing is taken once Done

    // The head and a first piece of the next answer in one read: the first answer ends at its end.
    f.reset();
    const std::string two = std::string(kOk) + std::string(kOk);
    CHECK(f.feed(two.data(), two.size()) == kOk.size());
    f.reset();
    CHECK(f.feed(two.data() + kOk.size(), kOk.size()) == kOk.size());
    CHECK(f.state() == Framer::State::Done && f.answer().body_ok);
}

void test_framer_faults() {
    for (const std::string_view text : {
             std::string_view("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"),
             std::string_view("HTTP/1.1 200 OK\r\ntransfer-encoding: chunked\r\nContent-Length: 13\r\n\r\n"),
             std::string_view("HTTP/1.1 200 OK\r\nServer: x\r\n\r\n"),  // 200 without a length
             std::string_view("garbage garbage\r\n\r\n"),
             std::string_view("HTTP/2 200 OK\r\nContent-Length: 13\r\n\r\n"),
             std::string_view("HTTP/1.1 20 OK\r\nContent-Length: 13\r\n\r\n"),
             std::string_view("HTTP/1.1 2000\r\nContent-Length: 13\r\n\r\n"),
             std::string_view("HTTP/1.1 200 OK\r\nContent-Length: 13abc\r\n\r\n"),
             std::string_view("HTTP/1.1 200 OK\r\nContent-Length: -1\r\n\r\n"),
             std::string_view("HTTP/1.1 200 OK\r\nContent-Length:\r\n\r\n"),
             std::string_view("HTTP/1.1 200 OK\r\nContent-Length: 1234567890123456789\r\n\r\n"),
             std::string_view("HTTP/1.1 200 OK\r\nContent-Length: 13\r\nContent-Length: 14\r\n\r\n"),
             std::string_view("HTTP/1.1 200 OK\r\nno colon here\r\nContent-Length: 13\r\n\r\n"),
             std::string_view("HTTP/1.1 200 OK\r\n: empty name\r\nContent-Length: 13\r\n\r\n"),
         }) {
        Framer f;
        const Fed r = feed_chunks(f, text, 1000);
        CHECK(r.state == Framer::State::Bad);
        CHECK(f.fault() != nullptr);
        Framer g;
        CHECK(feed_chunks(g, text, 1).state == Framer::State::Bad);
        CHECK(g.feed("x", 1) == 0);  // nothing is taken once Bad
    }
    // The same length twice is not a conflict.
    Framer f;
    CHECK(feed_chunks(f, "HTTP/1.1 200 OK\r\nContent-Length: 13\r\nContent-Length: 13\r\n\r\nHello, World!", 7).state ==
          Framer::State::Done);
    CHECK(f.answer().body_ok);
}

void test_framer_connection_header() {
    const auto close_of = [](std::string_view value) {
        Framer f;
        const std::string text = "HTTP/1.1 200 OK\r\nConnection: " + std::string(value) +
                                 "\r\nContent-Length: 13\r\n\r\nHello, World!";
        feed_chunks(f, text, 1000);
        CHECK(f.state() == Framer::State::Done);
        return f.answer().close;
    };
    CHECK(close_of("close"));
    CHECK(close_of("Close"));
    CHECK(close_of("keep-alive, close"));
    CHECK(close_of(" CLOSE "));
    CHECK(!close_of("keep-alive"));
    CHECK(!close_of("Keep-Alive"));
    CHECK(!close_of("closed"));
}

void test_framer_limits() {
    // A head that never ends.
    Framer f;
    const std::string junk(1000, 'a');
    bool bad = false;
    for (int i = 0; i < 40 && !bad; ++i) {
        f.feed(junk.data(), junk.size());
        bad = f.state() == Framer::State::Bad;
    }
    CHECK(bad);
    CHECK(f.fault() != nullptr);

    // A head that ends, but too late.
    Framer g;
    std::string long_head = "HTTP/1.1 200 OK\r\nX-Pad: " + std::string(kHeaderLimit, 'p') +
                            "\r\nContent-Length: 13\r\n\r\nHello, World!";
    CHECK(feed_chunks(g, long_head, long_head.size()).state == Framer::State::Bad);
    Framer h;
    CHECK(feed_chunks(h, long_head, 100).state == Framer::State::Bad);

    // A big but allowed head.
    Framer k;
    std::string ok_head = "HTTP/1.1 200 OK\r\nX-Pad: " + std::string(kHeaderLimit / 2, 'p') +
                          "\r\nContent-Length: 13\r\n\r\nHello, World!";
    CHECK(feed_chunks(k, ok_head, 333).state == Framer::State::Done);
    CHECK(k.answer().body_ok);

    // A body is never buffered: a long one is read as it comes and does not match.
    Framer b;
    constexpr std::string_view big_head = "HTTP/1.1 200 OK\r\nContent-Length: 1000000\r\n\r\n";
    b.feed(big_head.data(), big_head.size());
    CHECK(b.state() == Framer::State::Body);
    const std::string chunk(65536, 'z');
    std::uint64_t left = 1000000;
    while (left > 0) {
        left -= b.feed(chunk.data(), static_cast<std::size_t>(std::min<std::uint64_t>(chunk.size(), left)));
    }
    CHECK(b.state() == Framer::State::Done && !b.answer().body_ok);
}

// ---- command line --------------------------------------------------------------------------

ParsedOptions parse(std::vector<std::string> args) {
    return parse_options(args);
}

void test_options() {
    ParsedOptions p = parse({"--port", "8080", "--paths", "ring.txt"});
    CHECK(p.error.empty());
    CHECK(p.opts.host == "127.0.0.1" && p.opts.port == 8080 && p.opts.paths == "ring.txt");
    CHECK(p.opts.threads == 1 && p.opts.connections == 16);
    CHECK(p.opts.warmup_s == 1.0 && p.opts.duration_s == 5.0 && p.opts.timeout_ms == 1000);
    CHECK(p.opts.count == 0 && !p.opts.counting() && p.opts.cpus.empty() && p.opts.out.empty());

    p = parse({"--host", "10.1.2.3", "--port", "9", "--paths", "p", "--connections", "64", "--threads", "4", "--cpus",
               "2,4,6,8", "--warmup", "0.5", "--duration", "2.25", "--timeout-ms", "250", "--out", "r.json"});
    CHECK(p.error.empty());
    CHECK(p.opts.host == "10.1.2.3" && p.opts.port == 9 && p.opts.connections == 64 && p.opts.threads == 4);
    CHECK((p.opts.cpus == std::vector<int>{2, 4, 6, 8}) && p.opts.cpus_text == "2,4,6,8");
    CHECK(p.opts.warmup_s == 0.5 && p.opts.duration_s == 2.25 && p.opts.timeout_ms == 250 && p.opts.out == "r.json");

    // Count mode takes the timed options and ignores them.
    p = parse({"--port", "9", "--paths", "p", "--count", "100000", "--warmup", "1", "--duration", "5"});
    CHECK(p.error.empty() && p.opts.counting() && p.opts.count == 100000);

    // A thread without a connection has nothing to do.
    p = parse({"--port", "9", "--paths", "p", "--connections", "3", "--threads", "8"});
    CHECK(p.error.empty() && p.opts.threads == 3);

    p = parse({"--help"});
    CHECK(p.error.empty() && p.opts.help);
}

void test_options_bad() {
    const std::vector<std::vector<std::string>> bad = {
        {},                                                         // no port
        {"--port", "80"},                                           // no paths
        {"--paths", "p"},                                           // no port
        {"--port", "0", "--paths", "p"},
        {"--port", "65536", "--paths", "p"},
        {"--port", "80x", "--paths", "p"},
        {"--port", "", "--paths", "p"},
        {"--port", "80", "--paths", "p", "--bogus", "1"},
        {"--port", "80", "--paths", "p", "--depth", "1"},           // depth is always 1
        {"--port", "80", "--paths", "p", "--rate", "1000"},         // no open loop
        {"--port", "80", "--paths"},                                // a missing value
        {"--port", "80", "--paths", "p", "--connections", "0"},
        {"--port", "80", "--paths", "p", "--threads", "0"},
        {"--port", "80", "--paths", "p", "--timeout-ms", "0"},
        {"--port", "80", "--paths", "p", "--count", "0"},
        {"--port", "80", "--paths", "p", "--count", "-5"},
        {"--port", "80", "--paths", "p", "--count", "ten"},
        {"--port", "80", "--paths", "p", "--warmup", "-1"},
        {"--port", "80", "--paths", "p", "--warmup", "nan"},
        {"--port", "80", "--paths", "p", "--duration", "0"},
        {"--port", "80", "--paths", "p", "--duration", "1e9"},
        {"--port", "80", "--paths", "p", "--duration", "5s"},
        {"--port", "80", "--paths", "p", "--cpus", ""},
        {"--port", "80", "--paths", "p", "--cpus", "1,"},
        {"--port", "80", "--paths", "p", "--cpus", "a"},
        {"--port", "80", "--paths", "p", "--cpus", "-1"},
        {"--port", "80", "--paths", "p", "--cpus", "9999"},
    };
    for (const auto& args : bad) {
        const ParsedOptions p = parse(args);
        if (p.error.empty()) {
            std::string joined;
            for (const auto& a : args) {
                joined += a + " ";
            }
            std::fprintf(stderr, "accepted a bad command line: %s\n", joined.c_str());
        }
        CHECK(!p.error.empty());
    }
}

// ---- requests ------------------------------------------------------------------------------

void test_requests() {
    Requests r;
    std::string err = build_requests("/a\n/b/c\r\n\n/d", "127.0.0.1", 8080, r);
    CHECK(err.empty());
    CHECK(r.size() == 3);
    CHECK(r.get(0) == "GET /a HTTP/1.1\r\nHost: 127.0.0.1:8080\r\n\r\n");
    CHECK(r.get(1) == "GET /b/c HTTP/1.1\r\nHost: 127.0.0.1:8080\r\n\r\n");
    CHECK(r.get(2) == "GET /d HTTP/1.1\r\nHost: 127.0.0.1:8080\r\n\r\n");

    Requests with_newline;
    CHECK(build_requests("/x\n/y\n", "127.0.0.1", 1, with_newline).empty());
    CHECK(with_newline.size() == 2);

    for (const std::string_view bad : {std::string_view(""), std::string_view("\n\r\n\n"), std::string_view("a"),
                                       std::string_view("/a b"), std::string_view("/a\tb"),
                                       std::string_view("/a\x01"), std::string_view("/a\x7f")}) {
        Requests none;
        CHECK(!build_requests(bad, "127.0.0.1", 80, none).empty());
    }
    Requests huge;
    CHECK(!build_requests("/" + std::string(8192, 'a'), "127.0.0.1", 80, huge).empty());
    CHECK(build_requests("/" + std::string(8191, 'a'), "127.0.0.1", 80, huge).empty());
}

// ---- report --------------------------------------------------------------------------------

bool contains(const std::string& s, std::string_view what) {
    return s.find(what) != std::string::npos;
}

Totals sample_totals() {
    Totals t;
    t.measure.completed = 90;
    t.measure.status = 3;
    t.measure.body = 2;
    t.measure.framing = 1;
    t.measure.lost = 1;
    t.measure.timeouts = 3;
    t.measure.reconnects = 5;
    t.warmup.completed = 7;
    t.latency.add(1500);
    t.latency.add(2500);
    return t;
}

void test_report_count_has_no_time() {
    Options o;
    o.port = 8080;
    o.count = 100;
    o.connections = 8;
    o.threads = 2;
    o.warmup_s = 1.0;
    o.duration_s = 5.0;
    o.timeout_ms = 777;
    o.paths = "ring.txt";
    o.cpus_text = "1,2";
    const Totals t = sample_totals();
    const std::string line = render_count(o, "abc123", t);
    CHECK(line.front() == '{' && line.back() == '}');
    CHECK(line.find('\n') == std::string::npos);
    CHECK(contains(line, "\"mode\":\"count\""));
    CHECK(contains(line, "\"completed\":90"));
    CHECK(contains(line, "\"count\":100"));
    CHECK(contains(line, "\"resolved\":100"));
    CHECK(contains(line, "\"timeouts\":3"));
    CHECK(contains(line, "\"errors\":{\"status\":3,\"body\":2,\"framing\":1,\"lost\":1,\"unsolicited\":0}"));
    // Nothing that is, or looks like, a time, a rate or a window.
    for (const std::string_view word : {"_ns", "_ms", "_s\"", "latency", "wall", "MEASURE", "rate", "warmup",
                                        "duration", "t0", "t1", "777", "p50", "p99", "paths_file", "cpus"}) {
        if (contains(line, word)) {
            std::fprintf(stderr, "count line holds \"%.*s\": %s\n", static_cast<int>(word.size()), word.data(),
                         line.c_str());
        }
        CHECK(!contains(line, word));
    }
}

void test_report_timed() {
    Options o;
    o.port = 8080;
    o.connections = 8;
    o.threads = 2;
    o.paths = "C:\\work\\ring \"1\".txt";
    o.cpus_text = "1,2";
    const Totals t = sample_totals();
    const std::string line = render_timed(o, "abc123", 4096, 61, 1000, 6'000'001'000ULL, t);
    CHECK(line.front() == '{' && line.back() == '}');
    CHECK(line.find('\n') == std::string::npos);
    CHECK(contains(line, "\"mode\":\"timed\""));
    CHECK(contains(line, "\"measure_wall_ns\":6000000000"));
    CHECK(contains(line, "\"t0_ns\":1000"));
    CHECK(contains(line, "\"paths_file\":\"C:\\\\work\\\\ring \\\"1\\\".txt\""));
    CHECK(contains(line, "\"measure\":{\"completed\":90"));
    CHECK(contains(line, "\"warmup\":{\"completed\":7"));
    CHECK(contains(line, "\"latency_ns\":{\"count\":2"));
    CHECK(contains(line, "\"errors_total\":10"));  // 3 + 2 + 1 + 1 + 0 + 3
    CHECK(contains(line, "\"thread_failed\":0"));
    CHECK(!contains(line, "rate"));
}

void test_totals_and_exit_rules() {
    Stats a;
    Stats b;
    a.phase[1].completed = 10;
    a.phase[0].completed = 1;
    b.phase[1].completed = 20;
    b.phase[1].timeouts = 2;
    a.latency.add(100);
    b.latency.add(300);
    b.failed = true;
    Totals t;
    t.fold(a);
    t.fold(b);
    CHECK(t.measure.completed == 30 && t.warmup.completed == 1 && t.measure.timeouts == 2);
    CHECK(t.latency.count() == 2 && t.thread_failed);
    CHECK(!timed_ok(t));

    Options o;
    o.count = 100;
    Totals ok;
    ok.measure.completed = 100;
    CHECK(count_ok(o, ok) && timed_ok(ok));

    Totals fewer = ok;
    fewer.measure.completed = 99;
    CHECK(!count_ok(o, fewer));  // completed != N

    Totals timeout = ok;
    timeout.measure.completed = 99;
    timeout.measure.timeouts = 1;
    CHECK(!count_ok(o, timeout));

    Totals unsolicited = ok;  // every request completed, but the server sent more than it was asked
    unsolicited.measure.unsolicited = 1;
    CHECK(!count_ok(o, unsolicited));

    Totals miscount = ok;  // a request resolved twice: the instrument itself is wrong
    miscount.measure.status = 1;
    CHECK(!count_ok(o, miscount));

    Totals failed = ok;
    failed.thread_failed = true;
    CHECK(!count_ok(o, failed));

    Totals only_connects = ok;  // refused connections and reconnects alone are not request errors
    only_connects.measure.connect_errors = 12;
    only_connects.measure.reconnects = 12;
    CHECK(count_ok(o, only_connects));
}

}  // namespace

int main() {
    test_histogram_buckets();
    test_histogram_quantiles();
    test_histogram_merge();
    test_framer_good();
    test_framer_classes();
    test_framer_extra_and_reuse();
    test_framer_faults();
    test_framer_connection_header();
    test_framer_limits();
    test_options();
    test_options_bad();
    test_requests();
    test_report_count_has_no_time();
    test_report_timed();
    test_totals_and_exit_rules();
    if (g_failures != 0) {
        std::fprintf(stderr, "p2gen_tests: %d check(s) failed\n", g_failures);
        return 1;
    }
    std::printf("p2gen_tests: all checks passed\n");
    return 0;
}
