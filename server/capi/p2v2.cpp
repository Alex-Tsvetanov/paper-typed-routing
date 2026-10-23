// RegexMatcher v2 behind a C interface: see p2v2.h. The table is built and looked up as the C++
// server's v2 arm does it (server/src/arms.cpp: make_runtime_table, then find_into).
#include "p2v2.h"

#include <cstring>
#include <exception>
#include <string>
#include <string_view>
#include <vector>

#include <matcher/route.hpp>

#include "rb_isa.h"

namespace R = matcher::route;

#ifndef P2V2_BUILD_TYPE
#define P2V2_BUILD_TYPE "unknown"
#endif
#if defined(__clang__)
#define P2V2_COMPILER "clang " __clang_version__
#elif defined(_MSC_VER)
#define P2V2_STR2(x) #x
#define P2V2_STR(x) P2V2_STR2(x)
#define P2V2_COMPILER "MSVC " P2V2_STR(_MSC_FULL_VER)
#elif defined(__GNUC__)
#define P2V2_COMPILER "gcc " __VERSION__
#else
#define P2V2_COMPILER "unknown"
#endif
#ifdef NDEBUG
#define P2V2_NDEBUG "NDEBUG"
#else
#define P2V2_NDEBUG "no NDEBUG"
#endif

struct p2v2_table {
    R::RuntimeTable table;
    R::TableView view;
};

namespace {

// Copies a message without allocating, so no exception can leave the C interface from here.
void message(char* err, std::size_t errcap, const char* text) noexcept {
    if (err == nullptr || errcap == 0) {
        return;
    }
    const std::size_t len = std::strlen(text);
    const std::size_t n = len < errcap - 1 ? len : errcap - 1;
    std::memcpy(err, text, n);
    err[n] = '\0';
}

}  // namespace

extern "C" const char* p2v2_build_info(void) {
    return P2V2_COMPILER ", " P2V2_BUILD_TYPE ", " P2V2_NDEBUG ", isa " RB_ISA_TARGET_CPU;
}

extern "C" p2v2_table* p2v2_build(const char* const* patterns, const size_t* lens, size_t n, char* err,
                                  size_t errcap) {
    try {
        std::vector<R::RouteSpec> specs;
        specs.reserve(n);
        for (std::size_t i = 0; i < n; ++i) {
            specs.push_back({0, std::string_view(patterns[i], lens[i]), static_cast<std::uint32_t>(i)});
        }
        auto* t = new p2v2_table{R::make_runtime_table(specs), {}};
        if (t->table.error != R::BuildError::None) {
            const std::string text =
                "the routes do not build a table (route " + std::to_string(t->table.error_route) + ")";
            message(err, errcap, text.c_str());
            delete t;
            return nullptr;
        }
        t->view = t->table.view();
        return t;
    } catch (const std::exception& e) {
        message(err, errcap, e.what());
        return nullptr;
    } catch (...) {
        message(err, errcap, "unknown error");
        return nullptr;
    }
}

extern "C" void p2v2_free(p2v2_table* table) { delete table; }

extern "C" uint32_t p2v2_find(const p2v2_table* table, unsigned method, const char* path, size_t len, uint32_t* caps,
                              uint32_t max_caps, uint32_t* ncaps) {
    if (len > UINT32_MAX) {  // offsets go back as uint32; no HTTP path comes near it
        *ncaps = 0;
        return P2V2_NO_ROUTE;
    }
    R::Match m;
    R::find_into(table->view, method, std::string_view(path, len), m);
    if (m.status != R::Status::Found) {
        *ncaps = 0;
        return P2V2_NO_ROUTE;
    }
    const uint32_t n = m.count < max_caps ? m.count : max_caps;
    for (uint32_t i = 0; i < n; ++i) {
        caps[2 * i] = static_cast<uint32_t>(m.params[i].data() - path);
        caps[2 * i + 1] = static_cast<uint32_t>(m.params[i].size());
    }
    *ncaps = n;
    return m.route;
}
