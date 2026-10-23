//go:build windows

// v2 on Windows: a call into p2v2.dll, the C++ server's MSVC build of the C interface
// (server/capi/p2v2.h), without cgo. syscall.NewLazyDLL loads the DLL by an absolute path: the file
// named by the environment variable P2V2_DLL, else p2v2.dll next to this executable. The entry
// points are called through syscall.SyscallN. On Linux the same calls are cgo calls (v2_cgo.go).
// The two mechanisms cost differently per request, and that cost goes to v2.
//
// The pointers go to the library as uintptr values built inside the argument list of the call, so
// they stay valid for the call. The path bytes are kept alive across the call with
// runtime.KeepAlive. The pattern bytes given to p2v2_build are kept for the table's life: the
// library may keep views of them.
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"syscall"
	"unsafe"
)

type v2Table struct {
	handle   uintptr // the p2v2_table*
	findAddr uintptr // p2v2_find
	text     []byte  // the pattern bytes p2v2_build was given
}

func v2DLLPath() (string, error) {
	if p := os.Getenv("P2V2_DLL"); p != "" {
		return filepath.Abs(p)
	}
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	return filepath.Join(filepath.Dir(exe), "p2v2.dll"), nil
}

func newV2Table(patterns []string) (*v2Table, error) {
	path, err := v2DLLPath()
	if err != nil {
		return nil, fmt.Errorf("%w: %v", errV2Unavailable, err)
	}
	dll := syscall.NewLazyDLL(path)
	if err := dll.Load(); err != nil {
		return nil, fmt.Errorf("%w: %v (set P2V2_DLL to the DLL)", errV2Unavailable, err)
	}
	build, find := dll.NewProc("p2v2_build"), dll.NewProc("p2v2_find")
	for _, p := range []*syscall.LazyProc{build, find} {
		if err := p.Find(); err != nil {
			return nil, fmt.Errorf("%w: %v", errV2Unavailable, err)
		}
	}

	n := len(patterns)
	total := 0
	for _, p := range patterns {
		total += len(p)
	}
	text := make([]byte, total+1)
	ptrs := make([]uintptr, n+1)
	lens := make([]uintptr, n+1)
	off := 0
	for i, p := range patterns {
		copy(text[off:], p)
		ptrs[i] = uintptr(unsafe.Pointer(&text[off]))
		lens[i] = uintptr(len(p))
		off += len(p)
	}
	var errbuf [512]byte
	handle, _, _ := syscall.SyscallN(build.Addr(),
		uintptr(unsafe.Pointer(&ptrs[0])), uintptr(unsafe.Pointer(&lens[0])), uintptr(n),
		uintptr(unsafe.Pointer(&errbuf[0])), uintptr(len(errbuf)))
	runtime.KeepAlive(ptrs)
	runtime.KeepAlive(lens)
	if handle == 0 {
		return nil, v2Failure(cString(errbuf[:]))
	}
	return &v2Table{handle: handle, findAddr: find.Addr(), text: text}, nil
}

// find calls p2v2_find. The library returns a 32-bit value in EAX, so the upper half of the result
// register is not part of it.
func (t *v2Table) find(path string, vals *[maxCaptures]string) (uint32, int) {
	var caps [2 * maxCaptures]uint32
	var ncaps uint32
	r, _, _ := syscall.SyscallN(t.findAddr, t.handle, 0,
		uintptr(unsafe.Pointer(unsafe.StringData(path))), uintptr(len(path)),
		uintptr(unsafe.Pointer(&caps[0])), maxCaptures, uintptr(unsafe.Pointer(&ncaps)))
	runtime.KeepAlive(path)
	id := uint32(r)
	if id == v2NoRoute {
		return id, 0
	}
	return id, sliceCaptures(path, &caps, ncaps, vals)
}

// cString returns the bytes up to the first NUL.
func cString(b []byte) string {
	for i, c := range b {
		if c == 0 {
			return string(b[:i])
		}
	}
	return string(b)
}
