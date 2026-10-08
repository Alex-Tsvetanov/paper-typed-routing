// Unit tests of the minimal server's HTTP/1.1 layer (server/src/http1.hpp): the parser, the
// response bytes, HEAD and 405 (design/round2/minimal-server.md, sections 1 and 5). No test
// framework, so that a MemorySanitizer build needs no instrumented one.
#include <cstdio>
#include <cstdlib>
#include <new>
#include <string>
#include <string_view>
#include <vector>

#include "http1.hpp"

// ThreadSanitizer and MemorySanitizer define operator new and delete themselves, so the count of
// allocations per request is taken only in other builds.
#if defined(__has_feature)
#if __has_feature(thread_sanitizer) || __has_feature(memory_sanitizer)
#define MSERVER_NO_ALLOC_COUNT 1
#endif
#endif
#if defined(__SANITIZE_THREAD__)
#define MSERVER_NO_ALLOC_COUNT 1
#endif

namespace {

int g_failures = 0;
bool g_count = false;
long g_allocs = 0;

#define CHECK(cond)                                                                   \
    do {                                                                              \
        if (!(cond)) {                                                                \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
            ++g_failures;                                                             \
        }                                                                             \
    } while (0)

using namespace mserver;

const std::string kDate = "Wed, 30 Sep 2026 12:00:00 GMT";
const std::string kDate2 = "Thu, 01 Oct 2026 00:00:01 GMT";

// A router of fixed routes for the tests; every call is logged.
struct FakeRoute {
    unsigned method;
    std::string path;
    std::uint32_t route;
};
struct Fake {
    std::vector<FakeRoute> routes;
    mutable std::vector<unsigned> calls;
};

void fake_find(const void* data, unsigned method, std::string_view path, RouteResult& out) {
    const Fake& f = *static_cast<const Fake*>(data);
    f.calls.push_back(method);
    out.count = 0;
    out.allowed = 0;
    for (const FakeRoute& r : f.routes) {
        if (r.path == path && r.method == method) {
            out.status = RouteStatus::Found;
            out.route = r.route;
            return;
        }
    }
    for (const FakeRoute& r : f.routes) {
        if (r.path == path) {
            out.allowed = static_cast<std::uint16_t>(out.allowed | (1u << r.method));
        }
    }
    out.status = out.allowed ? RouteStatus::MethodNotAllowed : RouteStatus::NotFound;
}

std::string ok_head(std::string_view conn = "") {
    return "HTTP/1.1 200 OK\r\nDate: " + kDate + "\r\nContent-Type: text/plain\r\nContent-Length: 13\r\n" +
           std::string(conn) + "\r\n";
}

void test_parse_simple() {
    const std::string r = "GET /a/b?x=1 HTTP/1.1\r\nHost: h\r\n\r\n";
    const Parsed p = parse_request(r);
    CHECK(p.state == Parse::Complete);
    CHECK(p.consumed == r.size());
    CHECK(p.request.method == kGet);
    CHECK(p.request.target == "/a/b?x=1");
    CHECK(p.request.path == "/a/b");
    CHECK(p.request.minor == 1);
    CHECK(p.request.keep_alive);
    const Parsed h = parse_request("HEAD / HTTP/1.1\r\n\r\n");
    CHECK(h.state == Parse::Complete && h.request.method == kHead && h.request.path == "/");
    const char* names[] = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "CONNECT", "TRACE"};
    for (unsigned m = 0; m < kMethods; ++m) {
        const Parsed q = parse_request(std::string(names[m]) + " /x HTTP/1.1\r\n\r\n");
        CHECK(q.state == Parse::Complete && q.request.method == m);
    }
}

void test_parse_split_and_pipelined() {
    const std::string r = "GET /x HTTP/1.1\r\nHost: h\r\nUser-Agent: t\r\n\r\n";
    for (std::size_t n = 0; n < r.size(); ++n) {
        CHECK(parse_request(std::string_view(r).substr(0, n)).state == Parse::Incomplete);
    }
    CHECK(parse_request(r).state == Parse::Complete);
    const std::string three = "GET /1 HTTP/1.1\r\n\r\nGET /2 HTTP/1.1\r\nHost: h\r\n\r\nHEAD /3 HTTP/1.1\r\n\r\n";
    std::string_view rest = three;
    std::vector<std::string> paths;
    while (!rest.empty()) {
        const Parsed p = parse_request(rest);
        CHECK(p.state == Parse::Complete);
        if (p.state != Parse::Complete) break;
        paths.emplace_back(p.request.path);
        rest.remove_prefix(p.consumed);
    }
    CHECK((paths == std::vector<std::string>{"/1", "/2", "/3"}));
}

void test_parse_body_and_connection() {
    const std::string r = "POST /x HTTP/1.1\r\nContent-Length: 5\r\n\r\nhelloGET /y HTTP/1.1\r\n\r\n";
    const Parsed p = parse_request(r);
    CHECK(p.state == Parse::Complete && p.request.method == kPost);
    CHECK(p.consumed == r.find("GET"));
    CHECK(parse_request(std::string_view(r).substr(0, r.find("GET") - 2)).state == Parse::Incomplete);
    CHECK(!parse_request("GET / HTTP/1.1\r\nConnection: close\r\n\r\n").request.keep_alive);
    CHECK(!parse_request("GET / HTTP/1.1\r\nconnection: Foo, CLOSE\r\n\r\n").request.keep_alive);
    CHECK(parse_request("GET / HTTP/1.1\r\nConnection: keep-alive\r\n\r\n").request.keep_alive);
    const Parsed h10 = parse_request("GET / HTTP/1.0\r\n\r\n");
    CHECK(h10.state == Parse::Complete && h10.request.minor == 0 && !h10.request.keep_alive);
    CHECK(parse_request("GET / HTTP/1.0\r\nConnection: Keep-Alive\r\n\r\n").request.keep_alive);
    CHECK(parse_request("GET / HTTP/1.1\r\nX-Pad:   spaced value  \r\n\r\n").state == Parse::Complete);
}

void test_parse_refusals() {
    const auto refused = [](std::string_view r) {
        const Parsed p = parse_request(r);
        return p.state == Parse::Refused ? p.refusal : 0u;
    };
    CHECK(refused("POST /x HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n") == 501);
    CHECK(refused("FOO /x HTTP/1.1\r\n\r\n") == 501);
    CHECK(refused("GET http://h/x HTTP/1.1\r\n\r\n") == 400);
    CHECK(refused("OPTIONS * HTTP/1.1\r\n\r\n") == 400);
    CHECK(refused("GET /x\r\n\r\n") == 400);
    CHECK(refused("GET /x HTTP/2.0\r\n\r\n") == 400);
    CHECK(refused("GET  /x HTTP/1.1\r\n\r\n") == 400);
    CHECK(refused(" /x HTTP/1.1\r\n\r\n") == 400);
    CHECK(refused("GET /x HTTP/1.1\r\nNoColon\r\n\r\n") == 400);
    CHECK(refused("GET /x HTTP/1.1\r\nA: b\r\n folded\r\n\r\n") == 400);
    CHECK(refused("GET /x HTTP/1.1\r\nContent-Length: abc\r\n\r\n") == 400);
    CHECK(refused("GET /x HTTP/1.1\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n") == 400);
    CHECK(refused("GET /x HTTP/1.1\r\nBad Name: v\r\n\r\n") == 400);
    // A head of more than 8 KiB: refused whether or not its end has arrived.
    const std::string big = "GET /x HTTP/1.1\r\nX-Pad: " + std::string(kMaxHead, 'a');
    CHECK(refused(big) == 431);
    CHECK(refused(big + "\r\n\r\n") == 431);
    const std::string fits = "GET /x HTTP/1.1\r\nX: " + std::string(kMaxHead - 25, 'a') + "\r\n\r\n";
    CHECK(fits.size() <= kMaxHead);
    CHECK(parse_request(fits).state == Parse::Complete);
}

void test_responses() {
    Responses rs;
    rs.set_date(kDate);
    Fake f{{{kGet, "/g", 1}, {kHead, "/h", 2}, {kGet, "/h", 3}, {kPost, "/p", 4}, {kGet, "/gp", 5}, {kPost, "/gp", 6}}, {}};
    const Router router{fake_find, &f};
    RouteResult scratch;
    const auto answer = [&](std::string_view raw) {
        const Parsed p = parse_request(raw);
        std::string out;
        f.calls.clear();
        if (p.state == Parse::Complete) {
            rs.answer(p.request, router, scratch, out);
        }
        return out;
    };
    const std::string ok = ok_head() + "Hello, World!";
    CHECK(answer("GET /g HTTP/1.1\r\n\r\n") == ok);
    // HEAD: byte for byte the GET response up to the end of its header section, and no content.
    CHECK(answer("HEAD /g HTTP/1.1\r\n\r\n") == ok_head());
    CHECK((f.calls == std::vector<unsigned>{kHead, kGet}));
    // A HEAD route wins: the GET route is not asked.
    CHECK(answer("HEAD /h HTTP/1.1\r\n\r\n") == ok_head());
    CHECK((f.calls == std::vector<unsigned>{kHead}));
    // 405 with Allow; HEAD listed whenever GET is.
    const std::string na = "HTTP/1.1 405 Method Not Allowed\r\nDate: " + kDate + "\r\nContent-Length: 0\r\nAllow: ";
    CHECK(answer("GET /p HTTP/1.1\r\n\r\n") == na + "POST\r\n\r\n");
    CHECK(answer("PUT /gp HTTP/1.1\r\n\r\n") == na + "GET, HEAD, POST\r\n\r\n");
    CHECK(answer("HEAD /p HTTP/1.1\r\n\r\n") == na + "POST\r\n\r\n");
    // 404.
    const std::string nf = "HTTP/1.1 404 Not Found\r\nDate: " + kDate + "\r\nContent-Length: 0\r\n\r\n";
    CHECK(answer("GET /none HTTP/1.1\r\n\r\n") == nf);
    CHECK(answer("HEAD /none HTTP/1.1\r\n\r\n") == nf);
    // The connection's disposition.
    CHECK(answer("GET /g HTTP/1.1\r\nConnection: close\r\n\r\n") == ok_head("Connection: close\r\n") + "Hello, World!");
    CHECK(answer("GET /g HTTP/1.0\r\n\r\n") == ok_head("Connection: close\r\n") + "Hello, World!");
    CHECK(answer("GET /g HTTP/1.0\r\nConnection: keep-alive\r\n\r\n") ==
          ok_head("Connection: keep-alive\r\n") + "Hello, World!");
    CHECK(answer("GET /none HTTP/1.1\r\nConnection: close\r\n\r\n") ==
          "HTTP/1.1 404 Not Found\r\nDate: " + kDate + "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
    // Refusals close the connection.
    for (const auto& [status, reason] : {std::pair<unsigned, std::string_view>{400, "Bad Request"},
                                        {413, "Content Too Large"}, {431, "Request Header Fields Too Large"},
                                        {501, "Not Implemented"}}) {
        std::string out;
        rs.refuse(status, out);
        CHECK(out == "HTTP/1.1 " + std::to_string(status) + " " + std::string(reason) + "\r\nDate: " + kDate +
                         "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
    }
    // The Date field is patched in place.
    rs.set_date(kDate2);
    std::string out;
    rs.answer(parse_request("GET /g HTTP/1.1\r\n\r\n").request, router, scratch, out);
    CHECK(out.find(kDate2) != std::string::npos && out.find(kDate) == std::string::npos);
}

[[maybe_unused]] void test_no_allocation_per_request() {
    Responses rs;
    rs.set_date(kDate);
    Fake f{{{kGet, "/g", 1}, {kPost, "/p", 4}}, {}};
    f.calls.reserve(4096);
    const Router router{fake_find, &f};
    RouteResult scratch;
    std::string out;
    out.reserve(4096);
    const std::string reqs[] = {"GET /g HTTP/1.1\r\n\r\n", "HEAD /g HTTP/1.1\r\n\r\n", "GET /p HTTP/1.1\r\n\r\n",
                                "GET /none HTTP/1.1\r\n\r\n"};
    g_allocs = 0;
    g_count = true;
    for (int i = 0; i < 100; ++i) {
        for (const std::string& r : reqs) {
            out.clear();
            const Parsed p = parse_request(r);
            rs.answer(p.request, router, scratch, out);
        }
    }
    g_count = false;
    CHECK(g_allocs == 0);
}

}  // namespace

#ifndef MSERVER_NO_ALLOC_COUNT
void* operator new(std::size_t n) {
    if (g_count) {
        ++g_allocs;
    }
    if (void* p = std::malloc(n ? n : 1)) {
        return p;
    }
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
#endif

int main() {
    test_parse_simple();
    test_parse_split_and_pipelined();
    test_parse_body_and_connection();
    test_parse_refusals();
    test_responses();
#ifndef MSERVER_NO_ALLOC_COUNT
    test_no_allocation_per_request();
#else
    std::printf("test_http1: allocations per request not counted in this build\n");
#endif
    if (g_failures == 0) {
        std::printf("test_http1: all checks passed\n");
    }
    return g_failures == 0 ? 0 : 1;
}
