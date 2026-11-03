// regexmatcher-v2-goloop, a boundary arm of design/review-runs/boundary-arms.md: RegexMatcher v2 called from a
// Go loop, one Go-to-C call per lookup. v2's table is built here through its C functions
// (arms/capi/v2_goloop.cpp, a translation unit of its own); the Go side (arms/go/v2loop.go, in the Go arms'
// c-archive) gets a pointer to v2's lookup function and the table, and runs the throughput passes in the Go
// arms' structure (arms/gin.cpp): the ring's paths copied into Go once, the passes with the harness's 405
// rule inside Go, and a null pass in Go. The agreement test and the latency samples go from C++ into Go and
// from Go into v2, one call each way per lookup. No Go arm pays a Go-to-C call per lookup, so this arm shows
// what a Go program calling v2 would pay; it is not a symmetric comparison. Exploratory: it decides nothing.
#include <array>
#include <cstdint>
#include <new>
#include <string>
#include <vector>

#include "arms/capi/v2_capi.h"
#include "core/runner.hpp"
#include "regexmatcher_v2_goloop_sources.h"  // the digest of the Go module (cmake/ffi-go.cmake)

static_assert(sizeof(RB_FFI_SOURCES) > 1);

#ifndef RB_REGEXMATCHER_COMMIT
#define RB_REGEXMATCHER_COMMIT "unknown"
#endif

// The functions arms/go/v2loop.go and arms/go/main.go export.
extern "C" {
int rb_v2go_new(rb_v2go_find_fn find, void* table, std::uint32_t methods);
void rb_v2go_free(int h);
std::uint32_t rb_v2go_lookup(int h, int method, char* path, std::size_t n, std::uint32_t* caps, std::uint32_t max,
                             std::uint32_t* ncaps);
void rb_v2go_load(int h, std::size_t count, int* methods, char** paths, std::size_t* lens);
std::uint64_t rb_v2go_pass(int h, std::size_t n);
std::uint64_t rb_v2go_null_pass(int h, std::size_t n);
std::uint64_t rb_go_mallocs();
std::int64_t rb_go_heap();
void rb_go_nop();
int rb_go_procs();
std::uint64_t rb_go_gc_cycles();
}

namespace {

using namespace rb;

class V2GoloopArm final {
public:
    static ArmInfo info() {
        return {"regexmatcher-v2-goloop",
                std::string("RegexMatcher v2 ") + std::string(RB_REGEXMATCHER_COMMIT).substr(0, 9) +
                    " (table built at run time) called from a Go loop (cgo, one Go-to-C call per lookup)",
                "views into the path"};
    }

    V2GoloopArm() : table_(rb_v2goloop_new()) {
        if (table_ == nullptr) {
            throw std::bad_alloc();
        }
    }
    ~V2GoloopArm() {
        if (h_ >= 0) {
            rb_v2go_free(h_);
        }
        rb_v2goloop_free(table_);
    }
    V2GoloopArm(const V2GoloopArm&) = delete;
    V2GoloopArm& operator=(const V2GoloopArm&) = delete;

    void add(const Route& r, RouteId id) {
        const std::string pattern = render(r);
        std::array<char, 512> err{};
        if (rb_v2goloop_insert(table_, static_cast<std::uint32_t>(r.method), pattern.data(), pattern.size(), id,
                               err.data(), err.size()) != 0) {
            throw Refused(std::string("regexmatcher-v2-goloop: ") + err.data());
        }
        methods_ |= 1u << static_cast<unsigned>(r.method);
    }

    void finalize() {
        std::array<char, 512> err{};
        if (rb_v2goloop_finalize(table_, err.data(), err.size()) != 0) {
            throw Refused(std::string("regexmatcher-v2-goloop: ") + err.data());
        }
        h_ = rb_v2go_new(&rb_v2goloop_at, table_, methods_);
    }

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        std::array<std::uint32_t, 2 * kMaxParams> caps;
        std::uint32_t n = 0;
        const std::uint32_t id = rb_v2go_lookup(h_, static_cast<int>(m), const_cast<char*>(path.data()), path.size(),
                                                caps.data(), kMaxParams, &n);
        c.n = static_cast<std::uint8_t>(n);
        for (std::uint32_t i = 0; i < n; ++i) {
            c.v[i] = std::string_view(path).substr(caps[2 * i], caps[2 * i + 1]);
        }
        return id == 0xFFFF'FFFFu ? kNoRoute : id;
    }

    std::uint64_t pass(const Ring& r, std::size_t n) {
        load(r, n);
        return rb_v2go_pass(h_, n);
    }

    // The same loop over the same loaded data with no call to v2 in it (this arm's own null).
    std::uint64_t null_pass(const Ring& r, std::size_t n) {
        load(r, n);
        return rb_v2go_null_pass(h_, n);
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
            rb_v2go_load(h_, n, methods.data(), paths.data(), lens.data());
            loaded_ = &r;
            loaded_n_ = n;
        }
    }

    void* table_;
    int h_ = -1;
    std::uint32_t methods_ = 0;
    const Ring* loaded_ = nullptr;
    std::size_t loaded_n_ = 0;
};

}  // namespace

RB_ARM(V2GoloopArm)
