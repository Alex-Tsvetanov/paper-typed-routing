// The C function of the capi-null arm (arms/capi_null.cpp): an empty function with the shape of
// rb_v2capi_at (arms/capi/v2_capi.h), in a translation unit of its own, compiled apart from the arm's
// adapter without link-time optimisation. It reads the path's length and returns, as the C++ null arms'
// lookups do, so the arm's time per lookup is that of the harness's loop and one call across this
// boundary.
#include "arms/capi/v2_capi.h"

extern "C" uint32_t rb_capi_null_at(const void* /*arm*/, uint32_t /*method*/, const char* /*path*/, size_t len,
                                    uint32_t* /*caps*/, uint32_t /*max*/, uint32_t* ncaps) {
    *ncaps = 0;
    return static_cast<uint32_t>(len & 1u);
}
