// The C functions of the regexmatcher-v2-goloop arm (arms/regexmatcher_v2_goloop.cpp): RegexMatcher v2 in this
// translation unit of its own, behind the extern "C" functions of arms/capi/v2_capi.h (the code is
// arms/capi/v2_capi.hpp, as for regexmatcher-v2-capi). The Go loop (arms/go/v2loop.go) calls rb_v2goloop_at
// through a pointer the adapter hands it: one Go-to-C call per lookup.
#include "arms/capi/v2_capi.h"

#include <new>

#include "arms/capi/v2_capi.hpp"

namespace {

rb::capi::V2Table& table(void* arm) {
    return *static_cast<rb::capi::V2Table*>(arm);
}

}  // namespace

extern "C" void* rb_v2goloop_new(void) {
    return new (std::nothrow) rb::capi::V2Table;
}

extern "C" void rb_v2goloop_free(void* arm) {
    delete static_cast<rb::capi::V2Table*>(arm);
}

extern "C" int rb_v2goloop_insert(void* arm, uint32_t method, const char* pattern, size_t len, uint32_t id, char* err,
                                  size_t errcap) {
    return rb::capi::insert(table(arm), method, pattern, len, id, err, errcap);
}

extern "C" int rb_v2goloop_finalize(void* arm, char* err, size_t errcap) {
    return rb::capi::finalize(table(arm), err, errcap);
}

extern "C" uint32_t rb_v2goloop_at(const void* arm, uint32_t method, const char* path, size_t len, uint32_t* caps,
                                   uint32_t max, uint32_t* ncaps) {
    return rb::capi::at(*static_cast<const rb::capi::V2Table*>(arm), method, path, len, caps, max, ncaps);
}
