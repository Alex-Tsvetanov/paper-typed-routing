// The Go arms of rbench in one package, built with -buildmode=c-archive into one archive
// (cmake/ffi-go.cmake). Each c-archive carries its own Go runtime, so two of them cannot be
// linked into one executable; every Go router therefore lives in this module, one file per
// router: httprouter.go, nethttp.go and gin.go. Each file exports its own C functions and
// keeps its own handles. The functions here serve every Go arm but httprouter, whose own
// rb_hr_mallocs, rb_hr_heap and rb_hr_nop do the same.
package main

/*
#include <stddef.h>
#include <stdint.h>
*/
import "C"

import "runtime"

// The rbench methods in the order of rb::Method (core/route.hpp).
var methodNames = []string{"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}

// The Go runtime's count of heap allocations so far.
//
//export rb_go_mallocs
func rb_go_mallocs() C.uint64_t {
	var ms runtime.MemStats
	runtime.ReadMemStats(&ms)
	return C.uint64_t(ms.Mallocs)
}

// The bytes live on the Go heap after a collection.
//
//export rb_go_heap
func rb_go_heap() C.int64_t {
	runtime.GC()
	var ms runtime.MemStats
	runtime.ReadMemStats(&ms)
	return C.int64_t(ms.HeapAlloc)
}

// An empty cgo call, for the cost of the boundary (ffi_call_ns).
//
//export rb_go_nop
func rb_go_nop() {}

// GOMAXPROCS, as the runtime runs it (under the harness's pin to one CPU, 1), recorded with the
// timed passes.
//
//export rb_go_procs
func rb_go_procs() C.int {
	return C.int(runtime.GOMAXPROCS(0))
}

// The number of completed garbage collections, read before and after the timed passes.
//
//export rb_go_gc_cycles
func rb_go_gc_cycles() C.uint64_t {
	var ms runtime.MemStats
	runtime.ReadMemStats(&ms)
	return C.uint64_t(ms.NumGC)
}

func main() {}
