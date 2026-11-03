// RegexMatcher v2 behind a C interface, the code of the boundary arms of design/review-runs/boundary-arms.md
// (regexmatcher-v2-capi and regexmatcher-v2-goloop). Each of those arms compiles this into a translation
// unit of its own that exports extern "C" functions (arms/capi/v2_capi.cpp, arms/capi/v2_goloop.cpp), so its
// caller reaches v2 only through a call: rbench has no link-time optimisation, and a Go caller crosses cgo.
//
// The functions have the shape of the Rust arms' C functions (arms/rust/matchit_arm.rs): an opaque handle,
// the method as an index, the path as a pointer and a length, and the captured values written back as
// (offset, length) pairs into the path, with their count; the route id is returned, or 0xFFFFFFFF when
// the method has no route for the path. A 405 is not reported: the caller applies the harness's 405 rule,
// as it does for the Rust arms. The table is v2's, built at run time into one page-aligned block
// (make_runtime_table) after the last route, as the regexmatcher-v2 arm builds it (arms/rm_arm.hpp).
#pragma once

#include <matcher/route.hpp>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>

namespace rb::capi {

struct V2Table {
    std::vector<std::string> patterns;
    std::vector<unsigned> methods;
    std::vector<std::uint32_t> ids;
    matcher::route::RuntimeTable table;
    matcher::route::TableView view{};
};

inline void copy_error(const std::string& msg, char* err, std::size_t errcap) {
    if (errcap == 0) {
        return;
    }
    const std::size_t n = std::min(msg.size(), errcap - 1);
    std::memcpy(err, msg.data(), n);
    err[n] = '\0';
}

// Keeps one route until the build (0), or refuses it (1, with a message).
inline int insert(V2Table& t, std::uint32_t method, const char* pattern, std::size_t len, std::uint32_t id, char* err,
                  std::size_t errcap) {
    if (method >= matcher::route::kMethodSlots) {
        copy_error("method out of range", err, errcap);
        return 1;
    }
    t.patterns.emplace_back(pattern, len);
    t.methods.push_back(method);
    t.ids.push_back(id);
    return 0;
}

// Builds the table from the routes kept (0), or reports why it cannot (1).
inline int finalize(V2Table& t, char* err, std::size_t errcap) {
    std::vector<matcher::route::RouteSpec> specs;
    specs.reserve(t.patterns.size());
    for (std::size_t i = 0; i < t.patterns.size(); ++i) {
        specs.push_back({t.methods[i], t.patterns[i], t.ids[i]});
    }
    t.table = matcher::route::make_runtime_table(specs);
    if (t.table.error != matcher::route::BuildError::None) {
        copy_error("the routes do not build a table", err, errcap);
        return 1;
    }
    t.patterns = {};
    t.methods = {};
    t.ids = {};
    t.view = t.table.view();
    return 0;
}

// One lookup: the route id, or 0xFFFFFFFF; at most `max` captured values as (offset, length) pairs.
inline std::uint32_t at(const V2Table& t, std::uint32_t method, const char* path, std::size_t len,
                        std::uint32_t* caps, std::uint32_t max, std::uint32_t* ncaps) {
    const matcher::route::Match m = matcher::route::find(t.view, method, std::string_view(path, len));
    if (!m) {
        *ncaps = 0;
        return 0xFFFF'FFFFu;
    }
    const std::uint32_t n = m.count < max ? m.count : max;
    for (std::uint32_t i = 0; i < n; ++i) {
        caps[2 * i] = static_cast<std::uint32_t>(m.params[i].ptr - path);
        caps[2 * i + 1] = static_cast<std::uint32_t>(m.params[i].len);
    }
    *ncaps = n;
    return m.route;
}

}  // namespace rb::capi
