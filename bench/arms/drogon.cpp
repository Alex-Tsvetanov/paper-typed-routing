// Drogon's HTTP router, transcribed from drogon v1.9.13 (commit 4c5430757ea5,
// lib/src/HttpControllersRouter.cc, MIT licence). The router class needs a running
// drogon::app() and an HttpRequestImpl, so it cannot be driven on its own; this arm keeps its
// data structures and its lookup, line for line, and drops everything that is not routing
// (middlewares, CORS, response caches, query-string parameters, logging).
//
//   addHttpPath (.cc 335-598): each "{name}" placeholder becomes "([^/]*)". A path without
//     placeholders goes into ctrlMap_, an unordered_map keyed by the lower-cased path; a path
//     with placeholders goes into ctrlVector_, after a linear search for an item with the same
//     pattern. A catch-all has no placeholder form in Drogon; it is registered as a regex route
//     (registerHandlerViaRegex, addHttpRegex, .cc 316-333): "(.*)" after the literal prefix.
//   init (.cc 71-84): every item's regex is compiled with std::regex_constants::icase.
//   route (.cc 600-697): lower-case a copy of the path; try simpleCtrlMap_ (empty here, it
//     holds HttpSimpleController classes), then ctrlMap_; otherwise try each ctrlVector_ item
//     in registration order whose method slot is bound, with std::regex_match on the path.
//     The captures go into a new std::vector<std::string> by parameter place.
#include <algorithm>
#include <array>
#include <memory>
#include <regex>
#include <string>
#include <unordered_map>
#include <vector>

#include "core/runner.hpp"

namespace {

using namespace rb;

struct Binder {
    std::vector<std::size_t> parameterPlaces;
    RouteId id = kNoRoute;
};

struct RouterItem {
    std::string pathParameterPattern;
    std::string pathPattern;
    std::regex regex;
    std::array<std::shared_ptr<Binder>, kMethods> binders{};
};

class DrogonArm final {
public:
    static ArmInfo info() {
        return {"drogon", "drogonframework/drogon v1.9.13 (router lookup transcribed)", "std::vector<std::string> per match"};
    }

    void add(const Route& r, RouteId id) {
        std::string path;
        bool rest = false;
        std::size_t params = 0;
        for (const Segment& s : r.segs) {
            path += '/';
            if (s.kind == Seg::Literal) {
                path += s.text;
            } else if (s.kind == Seg::Param) {
                path += '{' + s.text + '}';
                ++params;
            } else {
                path += "(.*)";
                rest = true;
            }
        }
        auto binder = std::make_shared<Binder>();
        binder->id = id;
        const auto m = static_cast<std::size_t>(r.method);
        if (rest) {
            // addHttpRegex: the regex is its own pattern; captures keep their order.
            for (std::size_t i = 1; i <= params + 1; ++i) {
                binder->parameterPlaces.push_back(i);
            }
            addRegexCtrlBinder(binder, path, path, m);
            return;
        }
        static const std::regex placeholder("\\{([^/]*)\\}");
        for (std::size_t i = 1; i <= params; ++i) {
            binder->parameterPlaces.push_back(i);  // named placeholders take places 1, 2, ...
        }
        const std::string pathParameterPattern = std::regex_replace(path, placeholder, "([^/]*)");
        if (path != pathParameterPattern) {
            addRegexCtrlBinder(binder, path, pathParameterPattern, m);
            return;
        }
        std::string loweredPath;
        std::transform(path.begin(), path.end(), std::back_inserter(loweredPath),
                       [](unsigned char c) { return static_cast<char>(tolower(c)); });
        auto it = ctrlMap_.find(loweredPath);
        RouterItem* item = nullptr;
        if (it != ctrlMap_.end()) {
            item = &it->second;
        } else {
            RouterItem router;
            router.pathParameterPattern = pathParameterPattern;
            router.pathPattern = path;
            item = &ctrlMap_.emplace(loweredPath, std::move(router)).first->second;
        }
        item->binders[m] = binder;
    }

    void finalize() {
        for (auto& router : ctrlVector_) {
            router.regex = std::regex(router.pathParameterPattern, std::regex_constants::icase);
        }
        for (auto& p : ctrlMap_) {
            p.second.regex = std::regex(p.second.pathParameterPattern, std::regex_constants::icase);
        }
    }

    RouteId lookup(Method method, const std::string& path, Captures& c) {
        c.n = 0;
        const auto m = static_cast<std::size_t>(method);
        std::string loweredPath(path.length(), 0);
        std::transform(path.begin(), path.end(), loweredPath.begin(),
                       [](unsigned char ch) { return static_cast<char>(tolower(ch)); });
        {
            auto it = simpleCtrlMap_.find(loweredPath);
            if (it != simpleCtrlMap_.end()) {
                const auto& binder = it->second.binders[m];
                return binder ? binder->id : kNoRoute;
            }
        }
        RouterItem* routerItemPtr = nullptr;
        std::smatch result;
        auto it = ctrlMap_.find(loweredPath);
        if (it != ctrlMap_.end()) {
            routerItemPtr = &it->second;
        } else {
            for (auto& item : ctrlVector_) {
                if (item.binders[m] && std::regex_match(path, result, item.regex)) {
                    routerItemPtr = &item;
                    break;
                }
            }
        }
        if (routerItemPtr == nullptr) {
            return kNoRoute;
        }
        const auto& binder = routerItemPtr->binders[m];
        if (!binder) {
            return kNoRoute;  // Drogon answers 405 Method Not Allowed
        }
        std::vector<std::string> params;
        for (std::size_t j = 1; j < result.size(); ++j) {
            if (!result[j].matched) {
                continue;
            }
            std::size_t place = j;
            if (j <= binder->parameterPlaces.size()) {
                place = binder->parameterPlaces[j - 1];
            }
            if (place > params.size()) {
                params.resize(place);
            }
            params[place - 1] = result[j].str();
        }
        params_ = std::move(params);  // Drogon moves them into the request
        for (const std::string& v : params_) {
            if (c.n < kMaxParams) {
                c.v[c.n++] = v;
            }
        }
        return binder->id;
    }

private:
    void addRegexCtrlBinder(const std::shared_ptr<Binder>& binder, const std::string& pathPattern,
                            const std::string& pathParameterPattern, std::size_t m) {
        auto existRouter = std::find_if(ctrlVector_.begin(), ctrlVector_.end(), [&](const RouterItem& item) {
            return item.pathParameterPattern == pathParameterPattern;
        });
        RouterItem* item = nullptr;
        if (existRouter == ctrlVector_.end()) {
            RouterItem router;
            router.pathParameterPattern = pathParameterPattern;
            router.pathPattern = pathPattern;
            ctrlVector_.push_back(std::move(router));
            item = &ctrlVector_.back();
        } else {
            item = &*existRouter;
        }
        item->binders[m] = binder;
    }

    std::unordered_map<std::string, RouterItem> simpleCtrlMap_;
    std::unordered_map<std::string, RouterItem> ctrlMap_;
    std::vector<RouterItem> ctrlVector_;
    std::vector<std::string> params_;
};

}  // namespace

RB_ARM(DrogonArm)
