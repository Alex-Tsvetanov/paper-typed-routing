// Oat++'s URL router (oatpp::web::url::mapping::Router), one per method as HttpRouter keeps
// them (HttpRouter looks the method up in a map of these; the arm indexes them by rbench's method
// enum, as v2's adapter does). A parameter is {name} and a catch-all a trailing '*' (the URL tail).
// getRoute() tries the patterns in registration order and returns the first match. The path goes
// in as a StringKeyLabel over the query's bytes, as Oat++'s request parser hands it over. The
// values are read through the match map's public getVariables(), whose labels are views into the
// path, so no value is copied; the tail has no such accessor, and getTail() copies it into a new
// oatpp::String, which the arm keeps until the next lookup.
#include <oatpp/web/url/mapping/Router.hpp>

#include <array>
#include <memory>
#include <string>
#include <vector>

#include "core/runner.hpp"

namespace {

using namespace rb;
using oatpp::data::share::StringKeyLabel;

class OatppArm final {
public:
    static ArmInfo info() {
        return {"oatpp", "oatpp/oatpp 1.3.1", "views into the path (getVariables); an oatpp::String for the tail (getTail)"};
    }

    void add(const Route& r, RouteId id) {
        std::string pattern;
        Names names;
        for (const Segment& s : r.segs) {
            pattern += '/';
            if (s.kind == Seg::Literal) {
                pattern += s.text;
            } else if (s.kind == Seg::Param) {
                pattern += '{' + s.text + '}';
                names_text_.push_back(std::make_unique<std::string>(s.text));
                names.params.push_back(StringKeyLabel(names_text_.back()->c_str()));
            } else {
                pattern += '*';
                names.tail = true;
            }
        }
        if (names_.size() != id) {
            throw Refused("oatpp: route ids must be registered in order");
        }
        names_.push_back(std::move(names));
        routers_[static_cast<std::size_t>(r.method)].route(oatpp::String(pattern), id);
    }

    void finalize() {}

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        c.n = 0;
        auto route = routers_[static_cast<std::size_t>(m)].getRoute(
            StringKeyLabel(std::shared_ptr<std::string>(), path.data(), static_cast<v_buff_size>(path.size())));
        if (!route) {
            return kNoRoute;
        }
        const RouteId id = route.getEndpoint();
        const auto& vars = route.getMatchMap().getVariables();
        const Names& names = names_[id];
        for (const StringKeyLabel& name : names.params) {
            const auto it = vars.find(name);
            if (c.n < kMaxParams) {
                c.v[c.n++] = it == vars.end() ? std::string_view()
                                              : std::string_view(static_cast<const char*>(it->second.getData()),
                                                                 static_cast<std::size_t>(it->second.getSize()));
            }
        }
        if (names.tail) {
            tail_ = route.getMatchMap().getTail();
            if (c.n < kMaxParams) {
                c.v[c.n++] = tail_ ? std::string_view(*tail_) : std::string_view();
            }
        }
        return id;
    }

private:
    struct Names {
        std::vector<StringKeyLabel> params;  // over names_text_, which lives as long as the arm
        bool tail = false;
    };
    std::array<oatpp::web::url::mapping::Router<RouteId>, kMethods> routers_;
    std::vector<Names> names_;
    std::vector<std::unique_ptr<std::string>> names_text_;
    oatpp::String tail_;
};

}  // namespace

RB_ARM(OatppArm)
