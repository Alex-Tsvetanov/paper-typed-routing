// gin-gonic/gin's router (Go), through a cgo C interface (arms/go/gin.go). The route tree is
// gin's tree.go at v1.12.0, vendored unchanged (arms/go/gin), searched as gin's Engine
// searches it in its default configuration (arms/go/gin/rbshim.go): one tree per method,
// parameters and skipped nodes preallocated to the table's maximum counts, and the path taken
// as given with unescape false. A gin server hands the tree URL.Path, which net/url has
// already percent-decoded; this arm hands it the path as sent, as every other arm gets it. A
// parameter is :name and a catch-all *name, whose value keeps its leading '/'. Captured values
// come back as offsets into the query path, so they are views, except the values gin finds
// after a backtrack: getValue then continues in a copy of the path it rebuilds (prefix +
// path), and those values are copied into a buffer the adapter owns.
//
// gin answers 405 only with HandleMethodNotAllowed, which is off by default, so the harness's
// rule applies (not native_405). A miss that gin would answer with a trailing-slash redirect
// (RedirectTrailingSlash, on by default) is a miss here.
//
// As for httprouter, the throughput passes run inside Go over the ring's paths, loaded once
// (pass()); the agreement test and the latency samples go through one cgo call per lookup.
// Go's allocations and heap bytes are counted by the Go runtime.
#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include "core/runner.hpp"
#include "gin_sources.h"  // the digest of the Go module (cmake/ffi-go.cmake)

static_assert(sizeof(RB_FFI_SOURCES) > 1);

// The functions arms/go/gin.go and arms/go/main.go export.
extern "C" {
int rb_gin_new();
void rb_gin_free(int h);
int rb_gin_insert(int h, int method, char* pattern, std::size_t n, std::uint32_t id, char* errbuf, std::size_t errcap);
void rb_gin_finalize(int h);
std::uint32_t rb_gin_lookup(int h, int method, char* path, std::size_t n, char* buf, std::size_t bufcap,
                            std::uint32_t* caps, std::uint32_t max, std::uint32_t* ncaps);
void rb_gin_load(int h, std::size_t count, int* methods, char** paths, std::size_t* lens);
std::uint64_t rb_gin_pass(int h, std::size_t n);
std::uint64_t rb_gin_null_pass(int h, std::size_t n);
std::uint64_t rb_go_mallocs();
std::int64_t rb_go_heap();
void rb_go_nop();
int rb_go_procs();
std::uint64_t rb_go_gc_cycles();
}

namespace {

using namespace rb;

class GinArm final {
public:
    static ArmInfo info() {
        return {"gin", "gin-gonic/gin v1.12.0 tree.go (Go, cgo)", "views into the path (copies after a backtrack)"};
    }

    GinArm() : h_(rb_gin_new()) {}
    ~GinArm() { rb_gin_free(h_); }
    GinArm(const GinArm&) = delete;
    GinArm& operator=(const GinArm&) = delete;

    void add(const Route& r, RouteId id) {
        std::string pattern;
        for (const Segment& s : r.segs) {
            pattern += '/';
            pattern += s.kind == Seg::Literal ? s.text : (s.kind == Seg::Param ? ":" : "*") + s.text;
        }
        std::array<char, 512> err{};
        if (rb_gin_insert(h_, static_cast<int>(r.method), pattern.data(), pattern.size(), id, err.data(),
                          err.size()) != 0) {
            throw Refused(std::string("gin: ") + err.data());
        }
    }

    void finalize() { rb_gin_finalize(h_); }

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        // Values found after a backtrack come back copied into buf_ (offset bit 31 set); they
        // are disjoint parts of a rebuilt suffix of the path, so together no longer than it.
        buf_.resize(path.size() + 1);
        std::array<std::uint32_t, 2 * kMaxParams> caps;
        std::uint32_t n = 0;
        const std::uint32_t id = rb_gin_lookup(h_, static_cast<int>(m), const_cast<char*>(path.data()), path.size(),
                                               buf_.data(), buf_.size(), caps.data(), kMaxParams, &n);
        c.n = static_cast<std::uint8_t>(n);
        for (std::uint32_t i = 0; i < n; ++i) {
            const std::uint32_t off = caps[2 * i];
            c.v[i] = (off & kCopied) != 0 ? std::string_view(buf_.data() + (off & ~kCopied), caps[2 * i + 1])
                                          : std::string_view(path).substr(off, caps[2 * i + 1]);
        }
        return id == 0xFFFF'FFFFu ? kNoRoute : id;
    }

    std::uint64_t pass(const Ring& r, std::size_t n) {
        load(r, n);
        return rb_gin_pass(h_, n);
    }

    // The same loop over the same loaded data with no router in it (H2's null for this arm).
    std::uint64_t null_pass(const Ring& r, std::size_t n) {
        load(r, n);
        return rb_gin_null_pass(h_, n);
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
            rb_gin_load(h_, n, methods.data(), paths.data(), lens.data());
            loaded_ = &r;
            loaded_n_ = n;
        }
    }

    static constexpr std::uint32_t kCopied = 1u << 31;

    int h_;
    std::vector<char> buf_;
    const Ring* loaded_ = nullptr;
    std::size_t loaded_n_ = 0;
};

}  // namespace

RB_ARM(GinArm)
