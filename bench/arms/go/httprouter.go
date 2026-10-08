// A C interface to julienschmidt/httprouter for rbench (arms/httprouter.cpp), part of the
// one c-archive of the Go arms (main.go). One httprouter.Router holds every method, as in a
// Go server.
//
// A lookup reports the route id and each captured value as an offset and a length into the
// query path. A Go server finds the path in Go memory, so the throughput passes run inside Go
// (rb_hr_pass) over paths loaded once (rb_hr_load); a single lookup through rb_hr_lookup pays
// one cgo call, whose cost rb_hr_nop measures.
package main

/*
#include <stddef.h>
#include <stdint.h>
*/
import "C"

import (
	"fmt"
	"net/http"
	"runtime"
	"unsafe"

	"github.com/julienschmidt/httprouter"
)

type arm struct {
	router  *httprouter.Router
	last    uint32
	paths   []string
	meths   []string
	methods []string // the methods that have routes, in first-registered order
}

var arms []*arm

//export rb_hr_new
func rb_hr_new() C.int {
	arms = append(arms, &arm{router: httprouter.New()})
	return C.int(len(arms) - 1)
}

//export rb_hr_free
func rb_hr_free(h C.int) {
	arms[h] = nil
}

//export rb_hr_insert
func rb_hr_insert(h C.int, method C.int, pattern *C.char, n C.size_t, id C.uint32_t, errbuf *C.char, errcap C.size_t) (rc C.int) {
	a := arms[h]
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
	a.router.Handle(methodNames[method], path, func(http.ResponseWriter, *http.Request, httprouter.Params) { a.last = rid })
	known := false
	for _, m := range a.methods {
		known = known || m == methodNames[method]
	}
	if !known {
		a.methods = append(a.methods, methodNames[method])
	}
	return 0
}

//export rb_hr_lookup
func rb_hr_lookup(h C.int, method C.int, path *C.char, n C.size_t, caps *C.uint32_t, max C.uint32_t, ncaps *C.uint32_t) C.uint32_t {
	a := arms[h]
	p := unsafe.String((*byte)(unsafe.Pointer(path)), int(n))
	handle, ps, _ := a.router.Lookup(methodNames[method], p)
	if handle == nil {
		*ncaps = 0
		return 0xFFFFFFFF
	}
	handle(nil, nil, nil)
	out := unsafe.Slice((*C.uint32_t)(unsafe.Pointer(caps)), 2*int(max))
	base := uintptr(unsafe.Pointer(path))
	k := 0
	for _, prm := range ps {
		if k == int(max) {
			break
		}
		if len(prm.Value) > 0 {
			out[2*k] = C.uint32_t(uintptr(unsafe.Pointer(unsafe.StringData(prm.Value))) - base)
		} else {
			out[2*k] = 0
		}
		out[2*k+1] = C.uint32_t(len(prm.Value))
		k++
	}
	*ncaps = C.uint32_t(k)
	return C.uint32_t(a.last)
}

//export rb_hr_load
func rb_hr_load(h C.int, count C.size_t, methods *C.int, paths **C.char, lens *C.size_t) {
	a := arms[h]
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

// The throughput pass, inside Go: the lookups the harness makes through rb_hr_lookup, with
// the harness's 405 rule (on a miss, any other registered method that routes the path makes
// the answer 405), folded into the sink as the C++ harness folds them (detail::fold in
// core/runner.hpp): the route id, then every captured value's length and first byte.
//
//export rb_hr_pass
func rb_hr_pass(h C.int, n C.size_t) C.uint64_t {
	a := arms[h]
	var sum uint64
	for i := 0; i < int(n); i++ {
		id := uint64(0xFFFFFFFF)
		handle, ps, _ := a.router.Lookup(a.meths[i], a.paths[i])
		if handle != nil {
			handle(nil, nil, nil)
			id = uint64(a.last)
		} else {
			ps = nil
			for _, m := range a.methods {
				if m == a.meths[i] {
					continue
				}
				if other, _, _ := a.router.Lookup(m, a.paths[i]); other != nil {
					id = 0xFFFFFFFE
					break
				}
			}
		}
		sum += id
		for _, prm := range ps {
			sum += uint64(len(prm.Value))
			if len(prm.Value) > 0 {
				sum += uint64(prm.Value[0])
			}
		}
	}
	return C.uint64_t(sum)
}

// The null pass of rb_hr_pass: the same loop over the same loaded paths, the same 405 branch
// and the same sink, around a call that is never inlined and reads only the path's length
// instead of the router (hrNull). Its instructions per lookup are the loop's and the sink's,
// which H2 subtracts from rb_hr_pass's (hypotheses.md).
//
//export rb_hr_null_pass
func rb_hr_null_pass(h C.int, n C.size_t) C.uint64_t {
	a := arms[h]
	var sum uint64
	for i := 0; i < int(n); i++ {
		id := uint64(0xFFFFFFFF)
		rid, ps := hrNull(a.meths[i], a.paths[i])
		if rid != 0xFFFFFFFF {
			id = uint64(rid)
		} else {
			ps = nil
			for _, m := range a.methods {
				if m == a.meths[i] {
					continue
				}
				if other, _ := hrNull(m, a.paths[i]); other != 0xFFFFFFFF {
					id = 0xFFFFFFFE
					break
				}
			}
		}
		sum += id
		for _, prm := range ps {
			sum += uint64(len(prm.Value))
			if len(prm.Value) > 0 {
				sum += uint64(prm.Value[0])
			}
		}
	}
	return C.uint64_t(sum)
}

// hrNull stands for a.router.Lookup and the handle call in the null pass: it reads the path's
// length, finds a route (0 or 1) for every path, and captures nothing.
//
//go:noinline
func hrNull(method, path string) (uint32, httprouter.Params) {
	return uint32(len(path) & 1), nil
}

//export rb_hr_mallocs
func rb_hr_mallocs() C.uint64_t {
	var ms runtime.MemStats
	runtime.ReadMemStats(&ms)
	return C.uint64_t(ms.Mallocs)
}

//export rb_hr_heap
func rb_hr_heap() C.int64_t {
	runtime.GC()
	var ms runtime.MemStats
	runtime.ReadMemStats(&ms)
	return C.int64_t(ms.HeapAlloc)
}

//export rb_hr_nop
func rb_hr_nop() {}
