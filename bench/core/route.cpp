#include "core/route.hpp"

#include <stdexcept>

namespace rb {

std::string_view method_name(Method m) {
    switch (m) {
        case Method::Get: return "GET";
        case Method::Post: return "POST";
        case Method::Put: return "PUT";
        case Method::Delete: return "DELETE";
        case Method::Patch: return "PATCH";
        case Method::Head: return "HEAD";
        case Method::Options: return "OPTIONS";
    }
    return "GET";
}

std::string render(const Route& route) {
    std::string out;
    for (const Segment& s : route.segs) {
        out += '/';
        switch (s.kind) {
            case Seg::Literal: out += s.text; break;
            case Seg::Param: out += '{'; out += s.text; out += '}'; break;
            case Seg::Rest: out += "{*"; out += s.text; out += '}'; break;
        }
    }
    return out.empty() ? std::string("/") : out;
}

Route parse_route(Method method, std::string_view text) {
    if (text.empty() || text.front() != '/') {
        throw std::invalid_argument("route must start with '/': " + std::string(text));
    }
    Route r{method, {}};
    std::size_t pos = 1;
    while (pos <= text.size()) {
        const std::size_t slash = text.find('/', pos);
        const std::size_t end = slash == std::string_view::npos ? text.size() : slash;
        const std::string_view seg = text.substr(pos, end - pos);
        if (seg.empty()) {
            if (slash == std::string_view::npos && r.segs.empty()) {
                break;  // the root route "/"
            }
            throw std::invalid_argument("empty segment in route: " + std::string(text));
        }
        if (!r.segs.empty() && r.segs.back().kind == Seg::Rest) {
            throw std::invalid_argument("a catch-all must be the last segment: " + std::string(text));
        }
        if (seg.size() >= 3 && seg.front() == '{' && seg.back() == '}') {
            const bool rest = seg[1] == '*';
            const std::string_view name = seg.substr(rest ? 2 : 1, seg.size() - (rest ? 3 : 2));
            if (name.empty()) {
                throw std::invalid_argument("unnamed parameter in route: " + std::string(text));
            }
            r.segs.push_back({rest ? Seg::Rest : Seg::Param, std::string(name)});
        } else {
            r.segs.push_back({Seg::Literal, std::string(seg)});
        }
        if (slash == std::string_view::npos) {
            break;
        }
        pos = slash + 1;
    }
    return r;
}

}  // namespace rb
