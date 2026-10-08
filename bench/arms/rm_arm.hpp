// The adapter of RegexMatcher v2's arms: one class template for the table built at run time
// (regexmatcher-v2) and the table built while compiling (regexmatcher-v2-ct), which differ only
// in where the table view comes from. Both look up through rb::rm::find_v2, the one out-of-line
// copy of matcher::route::find (arms/regexmatcher_v2.cpp), so their lookups run the same machine
// code; the view is the adapter's first member, so every instantiation reads it at the same
// offset. The exploratory ablation arm (regexmatcher-v2-r1) instantiates the same template over
// the round-1 header, renamed (arms/ablation/route_r1.hpp).
#pragma once

#include <cstddef>
#include <cstdint>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "core/runner.hpp"

namespace rb::rm {

// The page offsets of a table's four arrays, as a JSON object for the cell's record; an empty
// array is null (it is never read, and where its pointer points is the standard library's choice).
template <class View>
std::string layout_of(const View& v) {
    const auto po = [](const auto& a) {
        return a.empty() ? std::string("null") : std::to_string(reinterpret_cast<std::uintptr_t>(a.data()) & 4095u);
    };
    return "{\"nodes\":" + po(v.nodes) + ",\"edges\":" + po(v.edges) + ",\"literals\":" + po(v.literals) +
           ",\"arena\":" + po(v.arena) + "}";
}

// Lib: the types, the build and the out-of-line lookup of one route matcher. Source: where the
// view comes from (RunTime builds it, CompileTime finds it among the compiled tables). Info:
// the arm's name and version.
template <class Lib, class Source, class Info>
class Arm final {
public:
    static constexpr bool native_405 = true;

    static ArmInfo info() { return Info::info(); }

    void add(const Route& r, RouteId id) { source_.add(r, id); }

    void finalize() { view_ = source_.template finalize<Lib>(); }

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        const typename Lib::Match r = Lib::find(view_, static_cast<unsigned>(m), path);
        c.n = r.count < kMaxParams ? r.count : static_cast<std::uint8_t>(kMaxParams);
        for (std::uint8_t i = 0; i < c.n; ++i) {
            c.v[i] = r.params[i];
        }
        if (r) {
            return r.route;
        }
        return r.status == Lib::kMethodNotAllowed ? kMethodNotAllowed : kNoRoute;
    }

    std::string table_layout() const { return layout_of(view_); }

private:
    typename Lib::TableView view_{};
    Source source_;
};

// The table built at run time: the patterns rendered in rbench's canonical syntax, then the
// library's build (Lib::build) after the last route.
template <class Lib>
class RunTime {
public:
    void add(const Route& r, RouteId id) {
        patterns_.push_back(render(r));
        methods_.push_back(static_cast<unsigned>(r.method));
        ids_.push_back(id);
    }

    template <class L>
    typename L::TableView finalize() {
        std::vector<typename L::RouteSpec> specs;
        specs.reserve(patterns_.size());
        for (std::size_t i = 0; i < patterns_.size(); ++i) {
            specs.push_back({methods_[i], patterns_[i], ids_[i]});
        }
        table_ = L::build(specs);
        if (table_.error != L::kBuildOk) {
            throw Refused("the routes do not build a table");
        }
        patterns_ = {};
        methods_ = {};
        ids_ = {};
        return table_.view();
    }

private:
    std::vector<std::string> patterns_;
    std::vector<unsigned> methods_;
    std::vector<RouteId> ids_;
    typename Lib::Built table_;
};

}  // namespace rb::rm
