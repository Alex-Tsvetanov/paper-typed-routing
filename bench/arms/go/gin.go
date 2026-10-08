// A C interface to the route tree of gin-gonic/gin for rbench (arms/gin.cpp). The tree is
// gin's own code at v1.12.0 (arms/go/gin, replacing the module github.com/gin-gonic/gin),
// searched as gin's Engine searches it (gin/rbshim.go): one tree per method, and parameters
// and skipped nodes preallocated to the table's maximum counts.
//
// A lookup reports the route id and each captured value as an offset and a length into the
// query path; with unescape false the tree's values are substrings of the path, except the
// values found after a backtrack, which rb_gin_lookup copies out. The throughput passes run
// inside Go (rb_gin_pass) over paths loaded once (rb_gin_load), as for httprouter.
package main

/*
#include <stddef.h>
#include <stdint.h>
*/
import "C"

import (
	"fmt"
	"unsafe"

	"github.com/gin-gonic/gin"
)

type ginArm struct {
	engine  *gin.RbEngine
	last    uint32
	paths   []string
	meths   []string
	methods []string // the methods that have routes, in first-registered order
}

var ginArms []*ginArm

//export rb_gin_new
func rb_gin_new() C.int {
	ginArms = append(ginArms, &ginArm{engine: gin.RbNew()})
	return C.int(len(ginArms) - 1)
}

//export rb_gin_free
func rb_gin_free(h C.int) {
	ginArms[h] = nil
}

// Returns 0, or 1 with gin's panic message, NUL-terminated, in errbuf.
//
//export rb_gin_insert
func rb_gin_insert(h C.int, method C.int, pattern *C.char, n C.size_t, id C.uint32_t, errbuf *C.char, errcap C.size_t) (rc C.int) {
	a := ginArms[h]
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
	a.engine.AddRoute(methodNames[method], path, gin.HandlersChain{func(*gin.Context) { a.last = rid }})
	known := false
	for _, m := range a.methods {
		known = known || m == methodNames[method]
	}
	if !known {
		a.methods = append(a.methods, methodNames[method])
	}
	return 0
}

//export rb_gin_finalize
func rb_gin_finalize(h C.int) {
	ginArms[h].engine.Prepare()
}

// lookup runs the route's handlers, as gin's Context.Next does, and returns the route id,
// or 0xFFFFFFFF when the method's tree has no route for the path.
func (a *ginArm) lookup(method, path string) (uint32, gin.Params) {
	handlers, ps := a.engine.Lookup(method, path)
	if handlers == nil {
		return 0xFFFFFFFF, nil
	}
	for _, handle := range handlers {
		handle(nil)
	}
	return a.last, ps
}

// Returns the route id, or 0xFFFFFFFF. Writes up to `max` captured values as (offset,
// length) pairs into caps and their count into ncaps. A value inside the query path is an
// offset into it. A value gin found after backtracking lies in the path gin rebuilt then
// (skippedNode.path, prefix + path); it is copied into buf (bufcap bytes) and its offset,
// into buf, has bit 31 set.
//
//export rb_gin_lookup
func rb_gin_lookup(h C.int, method C.int, path *C.char, n C.size_t, buf *C.char, bufcap C.size_t, caps *C.uint32_t, max C.uint32_t, ncaps *C.uint32_t) C.uint32_t {
	a := ginArms[h]
	p := unsafe.String((*byte)(unsafe.Pointer(path)), int(n))
	id, ps := a.lookup(methodNames[method], p)
	out := unsafe.Slice((*C.uint32_t)(unsafe.Pointer(caps)), 2*int(max))
	copied := unsafe.Slice((*byte)(unsafe.Pointer(buf)), int(bufcap))
	base := uintptr(unsafe.Pointer(path))
	used, k := 0, 0
	for _, prm := range ps {
		if k == int(max) {
			break
		}
		at := uintptr(unsafe.Pointer(unsafe.StringData(prm.Value)))
		switch {
		case len(prm.Value) == 0:
			out[2*k] = 0
		case at >= base && at+uintptr(len(prm.Value)) <= base+uintptr(n):
			out[2*k] = C.uint32_t(at - base)
		case used+len(prm.Value) <= len(copied):
			copy(copied[used:], prm.Value)
			out[2*k] = C.uint32_t(used) | 1<<31
			used += len(prm.Value)
		default:
			*ncaps = C.uint32_t(k)
			return C.uint32_t(id)
		}
		out[2*k+1] = C.uint32_t(len(prm.Value))
		k++
	}
	*ncaps = C.uint32_t(k)
	return C.uint32_t(id)
}

//export rb_gin_load
func rb_gin_load(h C.int, count C.size_t, methods *C.int, paths **C.char, lens *C.size_t) {
	a := ginArms[h]
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

// The throughput pass, inside Go: the lookups the harness makes through rb_gin_lookup, with
// the harness's 405 rule (gin's HandleMethodNotAllowed is off by default: on a miss, any
// other registered method that routes the path makes the answer 405), folded into the sink
// as the C++ harness folds them (detail::fold in core/runner.hpp): the route id, then every
// captured value's length and first byte.
//
//export rb_gin_null_pass
func rb_gin_null_pass(h C.int, n C.size_t) C.uint64_t {
	a := ginArms[h]
	var sum uint64
	for i := 0; i < int(n); i++ {
		id, ps := ginNull(a.meths[i], a.paths[i])
		if id == 0xFFFFFFFF {
			ps = nil
			for _, m := range a.methods {
				if m == a.meths[i] {
					continue
				}
				if other, _ := ginNull(m, a.paths[i]); other != 0xFFFFFFFF {
					id = 0xFFFFFFFE
					break
				}
			}
		}
		sum += uint64(id)
		for _, prm := range ps {
			sum += uint64(len(prm.Value))
			if len(prm.Value) > 0 {
				sum += uint64(prm.Value[0])
			}
		}
	}
	return C.uint64_t(sum)
}

// ginNull stands for a.lookup in the null pass of rb_gin_pass (the same loop over the same
// loaded paths, 405 branch and sink): it reads the path's length, finds a route for every
// path, and captures nothing.
//
//go:noinline
func ginNull(method, path string) (uint32, gin.Params) {
	return uint32(len(path) & 1), nil
}

//export rb_gin_pass
func rb_gin_pass(h C.int, n C.size_t) C.uint64_t {
	a := ginArms[h]
	var sum uint64
	for i := 0; i < int(n); i++ {
		id, ps := a.lookup(a.meths[i], a.paths[i])
		if id == 0xFFFFFFFF {
			ps = nil
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
		for _, prm := range ps {
			sum += uint64(len(prm.Value))
			if len(prm.Value) > 0 {
				sum += uint64(prm.Value[0])
			}
		}
	}
	return C.uint64_t(sum)
}
