/* RegexMatcher v2 behind a C interface, for the v2 arms of round 3's Go and Rust programs
 * (design/round3/end-to-end.md, section 1). It is compiled with the C++ server's compiler and flags,
 * so those arms run the code of the C++ server's v2 arm; only the language boundary differs, and it
 * counts against v2.
 *
 * Built as a static library (p2v2_c: Linux cgo, Rust) and as a shared one (p2v2: the Windows DLL
 * that the Go program calls without cgo). No C++ exception crosses the interface. */
#ifndef P2V2_H
#define P2V2_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32) && defined(P2V2_SHARED)
#if defined(P2V2_BUILD)
#define P2V2_API __declspec(dllexport)
#else
#define P2V2_API __declspec(dllimport)
#endif
#else
#define P2V2_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct p2v2_table p2v2_table;

/* No route matches. */
#define P2V2_NO_ROUTE 0xFFFFFFFFu

/* Builds v2's run-time table from n routes, route i being the GET route of pattern i in rbench's
 * syntax ("{p0}" a parameter, "{*p0}" the rest of the path), pattern i taking lens[i] bytes.
 * Returns NULL when the routes do not build a table, with a message in err (at most errcap bytes,
 * terminated). */
P2V2_API p2v2_table* p2v2_build(const char* const* patterns, const size_t* lens, size_t n, char* err,
                                size_t errcap);

P2V2_API void p2v2_free(p2v2_table* table);

/* Looks up one request: method as RegexMatcher v2 numbers them (0 is GET), and the path's len bytes.
 * Returns the route id, or P2V2_NO_ROUTE. Writes the captured values as (offset into path, length)
 * pairs into caps, 2 x max_caps entries at most, and their number into *ncaps. */
P2V2_API uint32_t p2v2_find(const p2v2_table* table, unsigned method, const char* path, size_t len, uint32_t* caps,
                            uint32_t max_caps, uint32_t* ncaps);

#ifdef __cplusplus
}
#endif

#endif
