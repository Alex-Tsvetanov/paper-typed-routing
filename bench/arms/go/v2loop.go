// RegexMatcher v2 called from a Go loop, for the regexmatcher-v2-goloop arm of
// design/review-runs/boundary-arms.md (arms/regexmatcher_v2_goloop.cpp). v2 is C++ (arms/capi/v2_goloop.cpp);
// this file holds no router. The adapter hands it a pointer to v2's lookup function (rb_v2goloop_at, the C
// shape of the Rust arms' functions) and v2's table, and every lookup here is one Go-to-C call through
// that pointer (rb_v2go_call). The pointer is passed at run time, so the archive has no reference to a
// symbol that only the arm's adapter defines, and builds without that arm link as before.
//
// The throughput passes run inside Go, in the Go arms' pass structure (gin.go): the paths copied into Go
// once (rb_v2go_load), the pass with the harness's 405 rule (on a miss, any other method with routes that
// routes the path makes the answer 405), the sink folded as the C++ harness folds it, and a null pass:
// the same loop over the same loaded paths with a Go function that reads only the path's length in place
// of the call to v2. So this arm's time net of its null pass includes the Go-to-C call.
package main

/*
#include <stddef.h>
#include <stdint.h>

typedef uint32_t (*rb_v2go_find_fn)(const void* arm, uint32_t method, const char* path, size_t len,
                                    uint32_t* caps, uint32_t max, uint32_t* ncaps);

// The one Go-to-C call of a lookup: v2's lookup through the pointer the adapter gave.
static inline uint32_t rb_v2go_call(rb_v2go_find_fn f, const void* arm, uint32_t method, const char* path,
                                    size_t len, uint32_t* caps, uint32_t max, uint32_t* ncaps) {
	return f(arm, method, path, len, caps, max, ncaps);
}
*/
import "C"

import "unsafe"

// The most captured values a lookup reports: rb::kMaxParams (core/route.hpp), as the adapter asks for.
const v2goMaxCaps = 8

type v2goArm struct {
	find    C.rb_v2go_find_fn
	table   unsafe.Pointer // v2's table, C++ memory
	caps    [2 * v2goMaxCaps]C.uint32_t
	ncaps   C.uint32_t
	paths   []string
	meths   []int32
	methods []int32 // the methods that have routes, in increasing order (as the harness tries them)
}

var v2goArms []*v2goArm

// A handle for v2's lookup function and table; methods has bit m set for every method with routes.
//
//export rb_v2go_new
func rb_v2go_new(find C.rb_v2go_find_fn, table unsafe.Pointer, methods C.uint32_t) C.int {
	a := &v2goArm{find: find, table: table}
	for m := int32(0); m < 32; m++ {
		if methods&(1<<uint(m)) != 0 {
			a.methods = append(a.methods, m)
		}
	}
	v2goArms = append(v2goArms, a)
	return C.int(len(v2goArms) - 1)
}

//export rb_v2go_free
func rb_v2go_free(h C.int) {
	v2goArms[h] = nil
}

// lookup is one Go-to-C call: the route id or 0xFFFFFFFF, and a.ncaps captured values in a.caps.
func (a *v2goArm) lookup(method int32, path string) uint32 {
	return uint32(C.rb_v2go_call(a.find, a.table, C.uint32_t(method), (*C.char)(unsafe.Pointer(unsafe.StringData(path))),
		C.size_t(len(path)), &a.caps[0], v2goMaxCaps, &a.ncaps))
}

// One lookup for the harness's agreement test and latency samples: from C into Go, and from Go into v2
// through the same pointer as the passes.
//
//export rb_v2go_lookup
func rb_v2go_lookup(h C.int, method C.int, path *C.char, n C.size_t, caps *C.uint32_t, max C.uint32_t, ncaps *C.uint32_t) C.uint32_t {
	a := v2goArms[h]
	return C.rb_v2go_call(a.find, a.table, C.uint32_t(method), path, n, caps, max, ncaps)
}

//export rb_v2go_load
func rb_v2go_load(h C.int, count C.size_t, methods *C.int, paths **C.char, lens *C.size_t) {
	a := v2goArms[h]
	ms := unsafe.Slice(methods, int(count))
	ps := unsafe.Slice(paths, int(count))
	ls := unsafe.Slice(lens, int(count))
	a.paths = make([]string, int(count))
	a.meths = make([]int32, int(count))
	for i := range a.paths {
		a.paths[i] = C.GoStringN(ps[i], C.int(ls[i]))
		a.meths[i] = int32(ms[i])
	}
}

// The throughput pass, inside Go: the lookups the harness makes through rb_v2go_lookup, with the
// harness's 405 rule, folded into the sink as the C++ harness folds them (detail::fold in
// core/runner.hpp): the route id, then every captured value's length and first byte.
//
//export rb_v2go_pass
func rb_v2go_pass(h C.int, n C.size_t) C.uint64_t {
	a := v2goArms[h]
	var sum uint64
	for i := 0; i < int(n); i++ {
		p := a.paths[i]
		id := a.lookup(a.meths[i], p)
		k := int(a.ncaps)
		if id == 0xFFFFFFFF {
			k = 0
			for _, m := range a.methods {
				if m == a.meths[i] {
					continue
				}
				if other := a.lookup(m, p); other != 0xFFFFFFFF {
					id = 0xFFFFFFFE
					break
				}
			}
		}
		sum += uint64(id)
		for j := 0; j < k; j++ {
			off, ln := int(a.caps[2*j]), int(a.caps[2*j+1])
			sum += uint64(ln)
			if ln > 0 {
				sum += uint64(p[off])
			}
		}
	}
	return C.uint64_t(sum)
}

// v2goNull stands for a.lookup in the null pass (the same loop over the same loaded paths, 405 branch
// and sink): it reads the path's length, finds a route for every path, and captures nothing. It is Go,
// so the null pass makes no Go-to-C call.
//
//go:noinline
func v2goNull(method int32, path string) (uint32, int) {
	return uint32(len(path) & 1), 0
}

//export rb_v2go_null_pass
func rb_v2go_null_pass(h C.int, n C.size_t) C.uint64_t {
	a := v2goArms[h]
	var sum uint64
	for i := 0; i < int(n); i++ {
		p := a.paths[i]
		id, k := v2goNull(a.meths[i], p)
		if id == 0xFFFFFFFF {
			k = 0
			for _, m := range a.methods {
				if m == a.meths[i] {
					continue
				}
				if other, _ := v2goNull(m, p); other != 0xFFFFFFFF {
					id = 0xFFFFFFFE
					break
				}
			}
		}
		sum += uint64(id)
		for j := 0; j < k; j++ {
			off, ln := int(a.caps[2*j]), int(a.caps[2*j+1])
			sum += uint64(ln)
			if ln > 0 {
				sum += uint64(p[off])
			}
		}
	}
	return C.uint64_t(sum)
}
