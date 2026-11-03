// The C interface of the regexmatcher-v2-capi arm (arms/regexmatcher_v2_capi.cpp): RegexMatcher v2 in this
// translation unit of its own, behind the extern "C" functions of arms/capi/v2_capi.h (the code is
// arms/capi/v2_capi.hpp). Compiled apart from the arm's adapter, without link-time optimisation, so the
// harness's timed loop reaches v2 through one call per lookup, as it reaches a Rust arm.
#include "arms/capi/v2_capi.h"

#include <new>

#include "arms/capi/v2_capi.hpp"

struct RbV2Capi {
    rb::capi::V2Table t;
};

extern "C" RbV2Capi* rb_v2capi_new(void) {
    return new (std::nothrow) RbV2Capi;
}

extern "C" void rb_v2capi_free(RbV2Capi* arm) {
    delete arm;
}

extern "C" int rb_v2capi_insert(RbV2Capi* arm, uint32_t method, const char* pattern, size_t len, uint32_t id,
                                char* err, size_t errcap) {
    return rb::capi::insert(arm->t, method, pattern, len, id, err, errcap);
}

extern "C" int rb_v2capi_finalize(RbV2Capi* arm, char* err, size_t errcap) {
    return rb::capi::finalize(arm->t, err, errcap);
}

extern "C" uint32_t rb_v2capi_at(const RbV2Capi* arm, uint32_t method, const char* path, size_t len, uint32_t* caps,
                                 uint32_t max, uint32_t* ncaps) {
    return rb::capi::at(arm->t, method, path, len, caps, max, ncaps);
}
