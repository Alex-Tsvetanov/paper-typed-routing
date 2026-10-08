// r3 (c9s/r3, the 2.0 branch), a C router that compiles each node's edges into one PCRE2
// pattern. One tree for all methods: a route carries its method bit and the match entry the
// request's. A parameter is {name} ([^/]+) and a catch-all {name:.*}, the form r3 compiles
// to its greedy opcode. r3_tree_compile() runs once after the last route. Each lookup
// creates and frees a match_entry, as r3's examples do; captures are views into the path.
extern "C" {
#include <r3.h>
}

#include <string>
#include <vector>

#include "core/runner.hpp"

namespace {

using namespace rb;

int method_bit(Method m) {
    switch (m) {
        case Method::Get: return METHOD_GET;
        case Method::Post: return METHOD_POST;
        case Method::Put: return METHOD_PUT;
        case Method::Delete: return METHOD_DELETE;
        case Method::Patch: return METHOD_PATCH;
        case Method::Head: return METHOD_HEAD;
        case Method::Options: return METHOD_OPTIONS;
    }
    return METHOD_GET;
}

class R3Arm final {
public:
    static ArmInfo info() { return {"r3", "c9s/r3 2.0 branch 83d362f8 (PCRE2 10.49)", "views into the path"}; }

    R3Arm() : tree_(r3_tree_create(10)) {}
    ~R3Arm() {
        if (entry_ != nullptr) {
            match_entry_free(entry_);
        }
        r3_tree_free(tree_);
    }
    R3Arm(const R3Arm&) = delete;
    R3Arm& operator=(const R3Arm&) = delete;

    void add(const Route& r, RouteId id) {
        std::string pattern;
        for (const Segment& s : r.segs) {
            pattern += '/';
            if (s.kind == Seg::Literal) {
                pattern += s.text;
            } else {
                pattern += '{' + s.text + (s.kind == Seg::Rest ? ":.*}" : "}");
            }
        }
        patterns_.push_back(std::make_unique<std::string>(std::move(pattern)));  // r3 keeps the pointer
        ids_.push_back(std::make_unique<RouteId>(id));
        char* err = nullptr;
        const std::string& p = *patterns_.back();
        if (r3_tree_insert_routel_ex(tree_, method_bit(r.method), p.c_str(), static_cast<int>(p.size()),
                                     ids_.back().get(), &err) == nullptr) {
            const std::string why = err != nullptr ? err : "insert failed";
            std::free(err);
            throw Refused("r3: " + why);
        }
    }

    void finalize() {
        char* err = nullptr;
        if (r3_tree_compile(tree_, &err) != 0) {
            const std::string why = err != nullptr ? err : "compile failed";
            std::free(err);
            throw Refused("r3: " + why);
        }
    }

    RouteId lookup(Method m, const std::string& path, Captures& c) {
        c.n = 0;
        if (entry_ != nullptr) {
            match_entry_free(entry_);
        }
        entry_ = match_entry_createl(path.c_str(), static_cast<int>(path.size()));
        entry_->request_method = method_bit(m);
        const R3Route* route = r3_tree_match_route(tree_, entry_);
        if (route == nullptr) {
            return kNoRoute;
        }
        for (unsigned i = 0; i < entry_->vars.tokens.size && c.n < kMaxParams; ++i) {
            const r3_iovec_t& t = entry_->vars.tokens.entries[i];
            c.v[c.n++] = std::string_view(t.base, t.len);
        }
        return *static_cast<const RouteId*>(route->data);
    }

private:
    R3Node* tree_;
    match_entry* entry_ = nullptr;
    std::vector<std::unique_ptr<std::string>> patterns_;
    std::vector<std::unique_ptr<RouteId>> ids_;
};

}  // namespace

RB_ARM(R3Arm)
