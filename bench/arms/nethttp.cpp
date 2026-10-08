// The ServeMux of Go's net/http, with the patterns of Go 1.22 and later, through a cgo C
// interface (arms/go/nethttp.go). One mux for every method, as a Go server has. A route is
// the pattern "METHOD /a/{name}", and a catch-all is "{name...}" at the end.
//
// A lookup calls ServeMux.ServeHTTP on an *http.Request, as the server does; each route's
// handler records its id and reads its values with r.PathValue. ServeMux.Handler(r) finds the
// handler too, but its documentation says that it does not populate the wildcards (PathValue
// then returns ""), so ServeHTTP is the documented way to both. PathValue returns the values
// percent-decoded, which need not be substrings of the path: they are copied into a buffer
// the adapter owns, and the captures are views into it.
//
// The mux decides 405 itself (native_405): when no pattern of the request's method matches
// and one of another method does. A GET pattern also matches HEAD. Every other answer that
// reaches no route handler is a miss with no captures: 404, and the 307 redirect of a path
// that is not in canonical form ("/a//b") or that names a subtree without its trailing slash
// ("/f" when "/f/{p...}" is registered), which a Go client would follow.
//
// Each request is built once per method and path, the first time the arm sees it, outside
// any timed loop: a server builds a request before routing it, so the allocations counted
// per lookup are those of ServeHTTP. As for httprouter, the throughput passes run inside Go
// over the ring's requests (pass()); the agreement test and the latency samples go through
// one cgo call per lookup. Go's allocations and heap bytes are counted by the Go runtime.
#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include "core/runner.hpp"
#include "nethttp_sources.h"  // the digest of the Go module (cmake/ffi-go.cmake)

static_assert(sizeof(RB_FFI_SOURCES) > 1);

#ifndef RB_NETHTTP_GO
#error "RB_NETHTTP_GO (the pinned Go version, cmake/pins.cmake) must be defined"
#endif

// The functions arms/go/nethttp.go and arms/go/main.go export.
extern "C" {
int rb_nh_new();
void rb_nh_free(int h);
int rb_nh_insert(int h, char* pattern, std::size_t n, std::uint32_t id, char* errbuf, std::size_t errcap);
std::uint32_t rb_nh_lookup(int h, int method, char* path, std::size_t n, char* buf, std::size_t bufcap,
                           std::uint32_t* lens, std::uint32_t max, std::uint32_t* ncaps);
void rb_nh_load(int h, std::size_t count, int* methods, char** paths, std::size_t* lens);
std::uint64_t rb_nh_pass(int h, std::size_t n);
std::uint64_t rb_nh_null_pass(int h, std::size_t n);
std::uint64_t rb_go_mallocs();
std::int64_t rb_go_heap();
void rb_go_nop();
int rb_go_procs();
std::uint64_t rb_go_gc_cycles();
}

namespace {

using namespace rb;

class NetHttpArm final {
public:
    static constexpr bool native_405 = true;

    static ArmInfo info() {
        return {"nethttp", std::string("net/http ServeMux, ") + RB_NETHTTP_GO + " (Go, cgo)",
                "copies (PathValue, percent-decoded)"};
    }

    NetHttpArm() : h_(rb_nh_new()) {}
    ~NetHttpArm() { rb_nh_free(h_); }
    NetHttpArm(const NetHttpArm&) = delete;
    NetHttpArm& operator=(const NetHttpArm&) = delete;

    void add(const Route& r, RouteId id) {
        std::string pattern(method_name(r.method));
        pattern += ' ';
        for (const Segment& s : r.segs) {
            pattern += '/';
            if (s.kind == Seg::Literal) {
                pattern += s.text;
            } else {
                pattern += '{' + s.text + (s.kind == Seg::Rest ? "...}" : "}");
            }
        }
        std::array<char, 512> err{};
        if (rb_nh_insert(h_, pattern.data(), pattern.size(), id, err.data(), err.size()) != 0) {
            throw Refused(std::string("nethttp: ") + err.data());
        }
    }

    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        // The values are disjoint parts of the path, decoded, so together no longer than it.
        buf_.resize(path.size() + 1);
        std::array<std::uint32_t, kMaxParams> lens;
        std::uint32_t n = 0;
        const std::uint32_t id = rb_nh_lookup(h_, static_cast<int>(m), const_cast<char*>(path.data()), path.size(),
                                              buf_.data(), buf_.size(), lens.data(), kMaxParams, &n);
        c.n = static_cast<std::uint8_t>(n);
        std::size_t off = 0;
        for (std::uint32_t i = 0; i < n; ++i) {
            c.v[i] = std::string_view(buf_.data() + off, lens[i]);
            off += lens[i];
        }
        return id;
    }

    std::uint64_t pass(const Ring& r, std::size_t n) {
        load(r, n);
        return rb_nh_pass(h_, n);
    }

    // The same loop over the same loaded data with no router in it (H2's null for this arm).
    std::uint64_t null_pass(const Ring& r, std::size_t n) {
        load(r, n);
        return rb_nh_null_pass(h_, n);
    }

    static std::uint64_t own_allocs() { return rb_go_mallocs(); }
    static std::int64_t own_live_bytes() { return rb_go_heap(); }
    static void ffi_nop() { rb_go_nop(); }
    static int runtime_procs() { return rb_go_procs(); }
    static std::uint64_t runtime_gc_cycles() { return rb_go_gc_cycles(); }

private:
    void load(const Ring& r, std::size_t n) {
        if (loaded_ != &r || loaded_n_ != n) {
            std::vector<int> methods;
            std::vector<char*> paths;
            std::vector<std::size_t> lens;
            for (std::size_t i = 0; i < n; ++i) {
                methods.push_back(static_cast<int>(r.queries[i].method));
                paths.push_back(const_cast<char*>(r.queries[i].path.data()));
                lens.push_back(r.queries[i].path.size());
            }
            rb_nh_load(h_, n, methods.data(), paths.data(), lens.data());
            loaded_ = &r;
            loaded_n_ = n;
        }
    }

    int h_;
    std::vector<char> buf_;
    const Ring* loaded_ = nullptr;
    std::size_t loaded_n_ = 0;
};

}  // namespace

RB_ARM(NetHttpArm)
