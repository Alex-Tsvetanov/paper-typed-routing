//go:build linux && p2v2cgo

// v2 on Linux: cgo calls into libp2v2_c.a, the static library of the C interface
// (server/capi/p2v2.h), built by the C++ server's build with clang and libstdc++. On Windows the
// same calls are DLL calls (v2_windows.go). The two mechanisms cost differently per request, and
// that cost goes to v2.
//
// Build, with the directory of libp2v2_c.a in CGO_LDFLAGS (the Go program does not know where the
// server's build tree is; in the dev image it is /home/dev/b/rel4/server):
//
//	CGO_ENABLED=1 CC=clang CXX=clang++ GOAMD64=v3 CGO_LDFLAGS="-L/home/dev/b/rel4/server" \
//	    go build -trimpath -tags p2v2cgo -o mserver-go-v2 .
//
// The header is found through -I${SRCDIR}/../capi below. p2v2_find keeps no pointer it is given and
// never calls back into Go, so "noescape" and "nocallback" hold for it. The buffers of a lookup
// then stay on the stack, as in the Windows file, and the call costs no allocation and no pool.
// p2v2_build copies the patterns, so the C memory that holds them is freed after the call.
package main

/*
#cgo CFLAGS: -I${SRCDIR}/../capi
#cgo LDFLAGS: -lp2v2_c -lstdc++
#cgo noescape p2v2_find
#cgo nocallback p2v2_find
#include <stdlib.h>
#include "p2v2.h"
*/
import "C"

import "unsafe"

type v2Table struct {
	table *C.p2v2_table
	info  string // p2v2_build_info
}

func newV2Table(patterns []string) (*v2Table, error) {
	n := len(patterns)
	total := 0
	for _, p := range patterns {
		total += len(p)
	}
	text := C.malloc(C.size_t(total + 1))
	ptrs := C.malloc(C.size_t(n+1) * C.size_t(unsafe.Sizeof(uintptr(0))))
	lens := C.malloc(C.size_t(n+1) * C.size_t(unsafe.Sizeof(C.size_t(0))))
	defer C.free(text)
	defer C.free(ptrs)
	defer C.free(lens)
	textBytes := unsafe.Slice((*byte)(text), total+1)
	ptrSlice := unsafe.Slice((**C.char)(ptrs), n+1)
	lenSlice := unsafe.Slice((*C.size_t)(lens), n+1)
	off := 0
	for i, p := range patterns {
		copy(textBytes[off:], p)
		ptrSlice[i] = (*C.char)(unsafe.Add(text, off))
		lenSlice[i] = C.size_t(len(p))
		off += len(p)
	}
	var errbuf [512]C.char
	table := C.p2v2_build((**C.char)(ptrs), (*C.size_t)(lens), C.size_t(n), &errbuf[0], C.size_t(len(errbuf)))
	if table == nil {
		return nil, v2Failure(C.GoString(&errbuf[0]))
	}
	return &v2Table{table: table, info: C.GoString(C.p2v2_build_info())}, nil
}

func (t *v2Table) find(path string, vals *[maxCaptures]string) (uint32, int) {
	var caps [2 * maxCaptures]uint32
	var ncaps uint32
	id := uint32(C.p2v2_find(t.table, 0, (*C.char)(unsafe.Pointer(unsafe.StringData(path))), C.size_t(len(path)),
		(*C.uint32_t)(unsafe.Pointer(&caps[0])), maxCaptures, (*C.uint32_t)(unsafe.Pointer(&ncaps))))
	if id == v2NoRoute {
		return id, 0
	}
	return id, sliceCaptures(path, &caps, ncaps, vals)
}

func (t *v2Table) describe() string { return v2Description("linked", t.info) }
