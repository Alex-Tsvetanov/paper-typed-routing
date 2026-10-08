// A C interface to go-chi/chi's router for rbench (arms/chi.cpp). The router is chi's own code
// at v5.3.2 (arms/go/chi, replacing the module github.com/go-chi/chi/v5), searched as chi's
// Mux searches it for a request (chi/rbshim.go): one Mux, a route context reset per lookup as
// the Mux resets its pooled one, the tree search, then the endpoint's handler, which records
// the route id. A parameter is {name} and a catch-all is *, whose value is the key "*".
//
// A lookup reports the route id and each captured value as an offset and a length into the
// query path: chi's values are substrings of the path it searched. The throughput passes run
// inside Go (rb_chi_pass) over paths loaded once (rb_chi_load), as for gin and httprouter.
package main

/*
#include <stddef.h>
#include <stdint.h>
*/
import "C"

import (
	"fmt"
	"net/http"
	"unsafe"

	"github.com/go-chi/chi/v5"
)

type chiArm struct {
	mux     *chi.Mux
	rctx    *chi.Context
	last    uint32
	paths   []string
	meths   []string
	methods []string // the methods that have routes, in first-registered order
}

var chiArms []*chiArm

//export rb_chi_new
func rb_chi_new() C.int {
	chiArms = append(chiArms, &chiArm{mux: chi.NewRouter(), rctx: chi.NewRouteContext()})
	return C.int(len(chiArms) - 1)
}

//export rb_chi_free
func rb_chi_free(h C.int) {
	chiArms[h] = nil
}

// Returns 0, or 1 with chi's panic message, NUL-terminated, in errbuf.
//
//export rb_chi_insert
func rb_chi_insert(h C.int, method C.int, pattern *C.char, n C.size_t, id C.uint32_t, errbuf *C.char, errcap C.size_t) (rc C.int) {
	a := chiArms[h]
	path := C.GoStringN(pattern, C.int(n))
	defer func() {
		if r := recover(); r != nil {
			msg := []byte(fmt.Sprint(r))
			out := unsafe.Slice((*byte)(unsafe.Pointer(errbuf)), int(errcap))
			k := copy(out[:len(out)-1], msg)
			out[k] = 0
			rc = 1
		}
	}()
	rid := uint32(id)
	a.mux.Method(methodNames[method], path, http.HandlerFunc(func(http.ResponseWriter, *http.Request) { a.last = rid }))
	known := false
	for _, m := range a.methods {
		known = known || m == methodNames[method]
	}
	if !known {
		a.methods = append(a.methods, methodNames[method])
	}
	return 0
}

// lookup finds the route as the Mux does and calls its handler, which records the route id; it
// returns 0xFFFFFFFF when no route of the method matches.
func (a *chiArm) lookup(method, path string) (uint32, []string) {
	h := a.mux.RbFind(a.rctx, method, path)
	if h == nil {
		return 0xFFFFFFFF, nil
	}
	h.ServeHTTP(nil, nil)
	return a.last, a.rctx.URLParams.Values
}

// Returns the route id, or 0xFFFFFFFF. Writes up to `max` captured values as (offset, length)
// pairs into caps and their count into ncaps; a value outside the query path (none is expected)
// ends the list.
//
//export rb_chi_lookup
func rb_chi_lookup(h C.int, method C.int, path *C.char, n C.size_t, caps *C.uint32_t, max C.uint32_t, ncaps *C.uint32_t) C.uint32_t {
	a := chiArms[h]
	p := unsafe.String((*byte)(unsafe.Pointer(path)), int(n))
	id, vs := a.lookup(methodNames[method], p)
	out := unsafe.Slice((*C.uint32_t)(unsafe.Pointer(caps)), 2*int(max))
	base := uintptr(unsafe.Pointer(path))
	k := 0
	for _, v := range vs {
		if k == int(max) {
			break
		}
		at := uintptr(unsafe.Pointer(unsafe.StringData(v)))
		switch {
		case len(v) == 0:
			out[2*k] = 0
		case at >= base && at+uintptr(len(v)) <= base+uintptr(n):
			out[2*k] = C.uint32_t(at - base)
		default:
			*ncaps = C.uint32_t(k)
			return C.uint32_t(id)
		}
		out[2*k+1] = C.uint32_t(len(v))
		k++
	}
	*ncaps = C.uint32_t(k)
	return C.uint32_t(id)
}

//export rb_chi_load
func rb_chi_load(h C.int, count C.size_t, methods *C.int, paths **C.char, lens *C.size_t) {
	a := chiArms[h]
	ms := unsafe.Slice(methods, int(count))
	ps := unsafe.Slice(paths, int(count))
	ls := unsafe.Slice(lens, int(count))
	a.paths = make([]string, int(count))
	a.meths = make([]string, int(count))
	for i := range a.paths {
		a.paths[i] = C.GoStringN(ps[i], C.int(ls[i]))
		a.meths[i] = methodNames[ms[i]]
	}
}

// The throughput pass, inside Go: the lookups the harness makes through rb_chi_lookup, with the
// harness's 405 rule (on a miss, any other registered method that routes the path makes the
// answer 405), folded into the sink as the C++ harness folds them (detail::fold in
// core/runner.hpp): the route id, then every captured value's length and first byte.
//
//export rb_chi_pass
func rb_chi_pass(h C.int, n C.size_t) C.uint64_t {
	a := chiArms[h]
	var sum uint64
	for i := 0; i < int(n); i++ {
		id, vs := a.lookup(a.meths[i], a.paths[i])
		if id == 0xFFFFFFFF {
			vs = nil
			for _, m := range a.methods {
				if m == a.meths[i] {
					continue
				}
				if other, _ := a.lookup(m, a.paths[i]); other != 0xFFFFFFFF {
					id = 0xFFFFFFFE
					break
				}
			}
		}
		sum += uint64(id)
		for _, v := range vs {
			sum += uint64(len(v))
			if len(v) > 0 {
				sum += uint64(v[0])
			}
		}
	}
	return C.uint64_t(sum)
}

// chiNull stands for a.lookup in the null pass (the same loop over the same loaded paths, 405
// branch and sink): it reads the path's length, finds a route for every path, and captures
// nothing.
//
//go:noinline
func chiNull(method, path string) (uint32, []string) {
	return uint32(len(path) & 1), nil
}

//export rb_chi_null_pass
func rb_chi_null_pass(h C.int, n C.size_t) C.uint64_t {
	a := chiArms[h]
	var sum uint64
	for i := 0; i < int(n); i++ {
		id, vs := chiNull(a.meths[i], a.paths[i])
		if id == 0xFFFFFFFF {
			vs = nil
			for _, m := range a.methods {
				if m == a.meths[i] {
					continue
				}
				if other, _ := chiNull(m, a.paths[i]); other != 0xFFFFFFFF {
					id = 0xFFFFFFFE
					break
				}
			}
		}
		sum += uint64(id)
		for _, v := range vs {
			sum += uint64(len(v))
			if len(v) > 0 {
				sum += uint64(v[0])
			}
		}
	}
	return C.uint64_t(sum)
}
