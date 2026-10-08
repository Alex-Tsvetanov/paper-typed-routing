// julienschmidt/httprouter (Go), through a cgo C interface (arms/go/httprouter.go). One
// router for every method, as a Go server has. A parameter is :name and a catch-all *name,
// whose value keeps its leading '/'. Captured values come back as offsets into the query
// path, so they are views.
//
// A cgo call costs about as much as a lookup, so the throughput passes run inside Go over the
// ring's paths, loaded into Go memory once (pass()); the per-lookup latency samples and the
// agreement test go through one cgo call per lookup, and ffi_call_ns reports the cost of an
// empty cgo call. Go's allocations and heap bytes are counted by the Go runtime
// (own_allocs(), and own_live_bytes() after a collection).
#include <array>
#include <cstdint>
#include <string>
#include <vector>

#include "core/runner.hpp"
#include "httprouter_sources.h"  // the digest of the Go module (cmake/ffi-go.cmake)

static_assert(sizeof(RB_FFI_SOURCES) > 1);

// The functions arms/go/httprouter.go exports (cgo writes the same declarations into the
// archive's header, which is not included so that no generated file is compiled here).
extern "C" {
int rb_hr_new();
void rb_hr_free(int h);
int rb_hr_insert(int h, int method, char* pattern, std::size_t n, std::uint32_t id, char* errbuf, std::size_t errcap);
std::uint32_t rb_hr_lookup(int h, int method, char* path, std::size_t n, std::uint32_t* caps, std::uint32_t max,
                           std::uint32_t* ncaps);
void rb_hr_load(int h, std::size_t count, int* methods, char** paths, std::size_t* lens);
std::uint64_t rb_hr_pass(int h, std::size_t n);
std::uint64_t rb_hr_null_pass(int h, std::size_t n);
std::uint64_t rb_hr_mallocs();
std::int64_t rb_hr_heap();
void rb_hr_nop();
int rb_go_procs();
std::uint64_t rb_go_gc_cycles();
}

namespace {

using namespace rb;

class HttpRouterArm final {
public:
    static ArmInfo info() {
        return {"httprouter", "julienschmidt/httprouter v1.3.0 (Go, cgo)", "views into the path"};
    }

    HttpRouterArm() : h_(rb_hr_new()) {}
    ~HttpRouterArm() { rb_hr_free(h_); }
    HttpRouterArm(const HttpRouterArm&) = delete;
    HttpRouterArm& operator=(const HttpRouterArm&) = delete;

    void add(const Route& r, RouteId id) {
        std::string pattern;
        for (const Segment& s : r.segs) {
            pattern += '/';
            pattern += s.kind == Seg::Literal ? s.text : (s.kind == Seg::Param ? ":" : "*") + s.text;
        }
        std::array<char, 512> err{};
        if (rb_hr_insert(h_, static_cast<int>(r.method), pattern.data(), pattern.size(), id, err.data(),
                         err.size()) != 0) {
            throw Refused(std::string("httprouter: ") + err.data());
        }
    }

    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        std::array<std::uint32_t, 2 * kMaxParams> caps;
        std::uint32_t n = 0;
        const std::uint32_t id = rb_hr_lookup(h_, static_cast<int>(m), const_cast<char*>(path.data()), path.size(),
                                              caps.data(), kMaxParams, &n);
        c.n = static_cast<std::uint8_t>(n);
        for (std::uint32_t i = 0; i < n; ++i) {
            c.v[i] = std::string_view(path).substr(caps[2 * i], caps[2 * i + 1]);
        }
        return id == 0xFFFF'FFFFu ? kNoRoute : id;
    }

    std::uint64_t pass(const Ring& r, std::size_t n) {
        load(r, n);
        return rb_hr_pass(h_, n);
    }

    // The same loop over the same loaded data with no router in it (H2's null for this arm).
    std::uint64_t null_pass(const Ring& r, std::size_t n) {
        load(r, n);
        return rb_hr_null_pass(h_, n);
    }

    static std::uint64_t own_allocs() { return rb_hr_mallocs(); }
    static std::int64_t own_live_bytes() { return rb_hr_heap(); }
    static void ffi_nop() { rb_hr_nop(); }
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
            rb_hr_load(h_, n, methods.data(), paths.data(), lens.data());
            loaded_ = &r;
            loaded_n_ = n;
        }
    }

    int h_;
    const Ring* loaded_ = nullptr;
    std::size_t loaded_n_ = 0;
};

}  // namespace

RB_ARM(HttpRouterArm)
