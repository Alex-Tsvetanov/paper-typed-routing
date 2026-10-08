// The minimal server's router arms: see arms.hpp.
#include "arms.hpp"

#include <fstream>
#include <stdexcept>

#include <matcher/route.hpp>

#include "arm_v1.hpp"

namespace mserver {

namespace {

namespace R = matcher::route;

struct V2 {
    R::RuntimeTable table;
    R::TableView view;
};

void find_v2(const void* data, unsigned method, std::string_view path, RouteResult& out) {
    R::find_into(static_cast<const V2*>(data)->view, method, path, out);
}

struct V1 {
    std::shared_ptr<v1::Router> router;
    v1::Lookup scratch;
};

// v1 finds for one method; 405 by asking the other methods, as rbench's harness does for an arm
// without one of its own.
void find_v1(const void* data, unsigned method, std::string_view path, RouteResult& out) {
    V1& a = *const_cast<V1*>(static_cast<const V1*>(data));  // the engine keeps its results between calls
    v1::match(*a.router, method, path, a.scratch);
    out.allowed = 0;
    if (a.scratch.route != 0xFFFF'FFFFu) {
        out.status = RouteStatus::Found;
        out.route = a.scratch.route;
        out.count = static_cast<std::uint8_t>(a.scratch.count < R::kMaxParams ? a.scratch.count : R::kMaxParams);
        for (std::uint8_t i = 0; i < out.count; ++i) {
            out.params[i] = R::Capture{a.scratch.values[i].data(), a.scratch.values[i].size()};
        }
        return;
    }
    out.count = 0;
    for (unsigned m = 0; m < kMethods; ++m) {
        if (m == method) {
            continue;
        }
        v1::match(*a.router, m, path, a.scratch);
        if (a.scratch.route != 0xFFFF'FFFFu) {
            out.allowed = static_cast<std::uint16_t>(out.allowed | (1u << m));
        }
    }
    out.status = out.allowed != 0 ? RouteStatus::MethodNotAllowed : RouteStatus::NotFound;
}

void find_null(const void*, unsigned, std::string_view, RouteResult& out) {
    out.status = RouteStatus::Found;
    out.count = 0;
    out.allowed = 0;
    out.route = 0;
}

}  // namespace

std::vector<RouteLine> read_routes(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("cannot read " + path);
    }
    std::vector<RouteLine> routes;
    std::string line;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        if (line.empty()) {
            continue;
        }
        if (line.rfind("GET /", 0) != 0) {
            throw std::runtime_error("routes file: not \"GET <pattern>\": " + line);
        }
        routes.push_back({kGet, line.substr(4)});
    }
    return routes;
}

Arm make_arm(std::string_view name, const std::vector<RouteLine>& routes) {
    if (name == "null") {
        return {Router{find_null, nullptr}, nullptr};
    }
    if (name != "v2" && name != "v1") {
        throw std::runtime_error("unknown router arm: " + std::string(name));
    }
    std::vector<R::RouteSpec> specs;
    bool has_root = false;
    for (std::size_t i = 0; i < routes.size(); ++i) {
        specs.push_back({routes[i].method, routes[i].pattern, static_cast<std::uint32_t>(i)});
        has_root = has_root || (routes[i].method == kGet && routes[i].pattern == "/");
    }
    if (!has_root) {
        specs.push_back({kGet, "/", static_cast<std::uint32_t>(routes.size())});
    }
    if (name == "v1") {
        std::vector<std::pair<unsigned, std::string>> v1_routes;
        for (const R::RouteSpec& spec : specs) {
            v1_routes.emplace_back(spec.method, std::string(spec.pattern));
        }
        auto a = std::make_shared<V1>();
        a->router = v1::make(v1_routes);
        return {Router{find_v1, a.get()}, a};
    }
    auto v2 = std::make_shared<V2>();
    v2->table = R::make_runtime_table(specs);
    if (v2->table.error != R::BuildError::None) {
        throw std::runtime_error("the routes do not build a table (route " + std::to_string(v2->table.error_route) + ")");
    }
    v2->view = v2->table.view();
    return {Router{find_v2, v2.get()}, v2};
}

}  // namespace mserver
