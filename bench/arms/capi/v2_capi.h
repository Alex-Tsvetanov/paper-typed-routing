/* The C interfaces of the C-boundary arms of design/review-runs/boundary-arms.md, in the shape of the Rust
 * arms' C functions (arms/rust/matchit_arm.rs):
 *   rb_v2capi_*     RegexMatcher v2 (arms/capi/v2_capi.cpp), for regexmatcher-v2-capi
 *   rb_capi_null_at an empty function of the same shape (arms/capi/null_capi.cpp), for capi-null
 *   rb_v2goloop_*   RegexMatcher v2 (arms/capi/v2_goloop.cpp), for regexmatcher-v2-goloop, whose Go loop
 *                   calls rb_v2goloop_at through a pointer of type rb_v2go_find_fn (arms/go/v2loop.go)
 * Each is defined in a translation unit of its own; rbench has no link-time optimisation, so a caller
 * reaches each only through a call. */
#ifndef RB_ARMS_CAPI_V2_CAPI_H
#define RB_ARMS_CAPI_V2_CAPI_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct RbV2Capi RbV2Capi;
RbV2Capi* rb_v2capi_new(void);
void rb_v2capi_free(RbV2Capi* arm);
int rb_v2capi_insert(RbV2Capi* arm, uint32_t method, const char* pattern, size_t len, uint32_t id, char* err,
                     size_t errcap);
int rb_v2capi_finalize(RbV2Capi* arm, char* err, size_t errcap);
uint32_t rb_v2capi_at(const RbV2Capi* arm, uint32_t method, const char* path, size_t len, uint32_t* caps,
                      uint32_t max, uint32_t* ncaps);

uint32_t rb_capi_null_at(const void* arm, uint32_t method, const char* path, size_t len, uint32_t* caps,
                         uint32_t max, uint32_t* ncaps);

typedef uint32_t (*rb_v2go_find_fn)(const void* arm, uint32_t method, const char* path, size_t len, uint32_t* caps,
                                    uint32_t max, uint32_t* ncaps);
void* rb_v2goloop_new(void);
void rb_v2goloop_free(void* arm);
int rb_v2goloop_insert(void* arm, uint32_t method, const char* pattern, size_t len, uint32_t id, char* err,
                       size_t errcap);
int rb_v2goloop_finalize(void* arm, char* err, size_t errcap);
uint32_t rb_v2goloop_at(const void* arm, uint32_t method, const char* path, size_t len, uint32_t* caps,
                        uint32_t max, uint32_t* ncaps);

#ifdef __cplusplus
}
#endif

#endif
