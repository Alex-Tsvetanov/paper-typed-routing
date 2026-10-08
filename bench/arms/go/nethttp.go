// A C interface to the ServeMux of Go's net/http for rbench (arms/nethttp.cpp), with the
// patterns of Go 1.22 and later: "GET /a/{p0}", and "{p1...}" for a catch-all at the end.
// One ServeMux holds every method, as in a Go server.
//
// A lookup goes through the documented API: ServeMux.ServeHTTP on an *http.Request and a
// response writer that keeps only the status. Each route's handler records the route id and
// reads the route's values with r.PathValue(name). ServeMux.Handler(r) would find the handler
// too, but its documentation says that it does not populate the wildcards, so that
// r.PathValue returns "". PathValue returns the values percent-decoded, which need not be
// substrings of the path, so rb_nh_lookup copies them into the caller's buffer.
//
// A request that reaches no route handler is a miss with no captures: 405 when the mux
// answers StatusMethodNotAllowed (a pattern of another method matches the path), 404 for any
// other answer. The other answers are 404 and the 307 redirects the mux sends for a path that
// is not in canonical form ("/a//b", "/a/./b") or that names a subtree without its trailing
// slash ("/f" when "/f/{p...}" is registered).
//
// A request's fields are those net/http's server sets from a request line (url.ParseRequestURI
// of the target): a server builds each request before routing, so building it is not part of
// a lookup, and the allocations counted per lookup are those of ServeHTTP. The throughput
// passes run inside Go (rb_nh_pass) over one request that is reused for every query, its
// method, path, raw path and target set from the ring's parsed targets (rb_nh_load), as the
// harness reads the ring from one compact copy; a single lookup through rb_nh_lookup pays one
// cgo call and routes a request built for that method and target.
package main

/*
#include <stddef.h>
#include <stdint.h>
*/
import "C"

import (
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"unsafe"
)

// statusWriter is an http.ResponseWriter that keeps the first status written and drops the
// body. Header() is a real map: http.Error and http.Redirect set headers on it.
type statusWriter struct {
	header http.Header
	status int
}

func (w *statusWriter) Header() http.Header { return w.header }

func (w *statusWriter) Write(b []byte) (int, error) {
	if w.status == 0 {
		w.status = http.StatusOK
	}
	return len(b), nil
}

func (w *statusWriter) WriteHeader(code int) {
	if w.status == 0 {
		w.status = code
	}
}

type nhKey struct {
	method int
	target string
}

type nhArm struct {
	mux   *http.ServeMux
	w     statusWriter
	hit   bool
	last  uint32
	vals  []string // the values of the last route found, in pattern order
	built map[nhKey]*http.Request
	// The ring for the passes: per query its method and the fields url.ParseRequestURI gives
	// its target, and the one request they are copied into.
	meths    []string
	paths    []string
	rawPaths []string
	targets  []string
	ok       []bool
	req      *http.Request
}

// nhRoute is one route's handler: it records the route id and reads the route's values.
type nhRoute struct {
	arm   *nhArm
	id    uint32
	names []string
}

func (h *nhRoute) ServeHTTP(_ http.ResponseWriter, r *http.Request) {
	a := h.arm
	a.hit = true
	a.last = h.id
	a.vals = a.vals[:0]
	for _, name := range h.names {
		a.vals = append(a.vals, r.PathValue(name))
	}
}

var nhArms []*nhArm

//export rb_nh_new
func rb_nh_new() C.int {
	a := &nhArm{mux: http.NewServeMux(), w: statusWriter{header: http.Header{}}, vals: make([]string, 0, 8),
		built: map[nhKey]*http.Request{}}
	nhArms = append(nhArms, a)
	return C.int(len(nhArms) - 1)
}

//export rb_nh_free
func rb_nh_free(h C.int) {
	nhArms[h] = nil
}

// wildcardNames returns the names of a pattern's wildcards, "{name}" or "{name...}", in order.
func wildcardNames(pattern string) []string {
	var names []string
	for _, seg := range strings.Split(pattern, "/") {
		if len(seg) > 2 && seg[0] == '{' && seg[len(seg)-1] == '}' {
			names = append(names, strings.TrimSuffix(seg[1:len(seg)-1], "..."))
		}
	}
	return names
}

// Registers "METHOD /path". Returns 0, or 1 with the mux's panic message, NUL-terminated, in
// errbuf (an invalid pattern, or one that conflicts with a registered pattern).
//
//export rb_nh_insert
func rb_nh_insert(h C.int, pattern *C.char, n C.size_t, id C.uint32_t, errbuf *C.char, errcap C.size_t) (rc C.int) {
	a := nhArms[h]
	p := C.GoStringN(pattern, C.int(n))
	defer func() {
		if r := recover(); r != nil {
			msg := []byte(fmt.Sprint(r))
			out := unsafe.Slice((*byte)(unsafe.Pointer(errbuf)), int(errcap))
			k := copy(out[:len(out)-1], msg)
			out[k] = 0
			rc = 1
		}
	}()
	a.mux.Handle(p, &nhRoute{arm: a, id: uint32(id), names: wildcardNames(p)})
	return 0
}

// newRequest builds the request of a request line "METHOD target HTTP/1.1", as the server
// does (http.ReadRequest), or nil when the target does not parse (the server answers 400
// then, before any routing).
func newRequest(method, target string) *http.Request {
	u, err := url.ParseRequestURI(target)
	if err != nil {
		return nil
	}
	return &http.Request{Method: method, URL: u, Proto: "HTTP/1.1", ProtoMajor: 1, ProtoMinor: 1,
		Header: http.Header{}, Host: "rbench", RequestURI: target}
}

// request returns the request for a method and a target that points at C memory, building
// it (with its own copy of the target) the first time.
func (a *nhArm) request(method C.int, target *C.char, n C.size_t) *http.Request {
	if r, ok := a.built[nhKey{int(method), unsafe.String((*byte)(unsafe.Pointer(target)), int(n))}]; ok {
		return r
	}
	t := C.GoStringN(target, C.int(n))
	r := newRequest(methodNames[method], t)
	a.built[nhKey{int(method), t}] = r
	return r
}

// serve runs one request through the mux. It returns the route id, 0xFFFFFFFE for 405 or
// 0xFFFFFFFF for any other miss; a.vals holds the route's values, and nothing on a miss.
func (a *nhArm) serve(r *http.Request) uint32 {
	a.hit = false
	a.vals = a.vals[:0]
	if r == nil {
		return 0xFFFFFFFF
	}
	a.w.status = 0
	a.mux.ServeHTTP(&a.w, r)
	if a.w.status != 0 {
		clear(a.w.header)
	}
	switch {
	case a.hit:
		return a.last
	case a.w.status == http.StatusMethodNotAllowed:
		return 0xFFFFFFFE
	default:
		return 0xFFFFFFFF
	}
}

// Returns the route id, 0xFFFFFFFE (405) or 0xFFFFFFFF (a miss). Copies up to `max` captured
// values one after another into buf (bufcap bytes), their lengths into lens and their count
// into ncaps.
//
//export rb_nh_lookup
func rb_nh_lookup(h C.int, method C.int, path *C.char, n C.size_t, buf *C.char, bufcap C.size_t, lens *C.uint32_t, max C.uint32_t, ncaps *C.uint32_t) C.uint32_t {
	a := nhArms[h]
	id := a.serve(a.request(method, path, n))
	out := unsafe.Slice((*byte)(unsafe.Pointer(buf)), int(bufcap))
	ls := unsafe.Slice((*C.uint32_t)(unsafe.Pointer(lens)), int(max))
	off, k := 0, 0
	for _, v := range a.vals {
		if k == int(max) || off+len(v) > len(out) {
			break
		}
		copy(out[off:], v)
		ls[k] = C.uint32_t(len(v))
		off += len(v)
		k++
	}
	*ncaps = C.uint32_t(k)
	return C.uint32_t(id)
}

//export rb_nh_load
func rb_nh_load(h C.int, count C.size_t, methods *C.int, paths **C.char, lens *C.size_t) {
	a := nhArms[h]
	ms := unsafe.Slice(methods, int(count))
	ps := unsafe.Slice(paths, int(count))
	ls := unsafe.Slice(lens, int(count))
	n := int(count)
	a.meths, a.paths, a.rawPaths = make([]string, n), make([]string, n), make([]string, n)
	a.targets, a.ok = make([]string, n), make([]bool, n)
	for i := 0; i < n; i++ {
		t := C.GoStringN(ps[i], C.int(ls[i]))
		a.meths[i], a.targets[i] = methodNames[ms[i]], t
		if u, err := url.ParseRequestURI(t); err == nil {
			a.paths[i], a.rawPaths[i], a.ok[i] = u.Path, u.RawPath, true
		}
	}
	a.req = newRequest("GET", "/")
}

// next sets the pass's one request to query i: its method, path, raw path and target. It
// returns nil for a target that does not parse (the server answers 400 before routing).
func (a *nhArm) next(i int) *http.Request {
	if !a.ok[i] {
		return nil
	}
	r := a.req
	r.Method, r.RequestURI = a.meths[i], a.targets[i]
	r.URL.Path, r.URL.RawPath = a.paths[i], a.rawPaths[i]
	return r
}

// The throughput pass, inside Go: the lookups the harness makes through rb_nh_lookup (the
// mux decides 405 itself), folded into the sink as the C++ harness folds them (detail::fold
// in core/runner.hpp): the route id, then every captured value's length and first byte.
//
//export rb_nh_pass
func rb_nh_pass(h C.int, n C.size_t) C.uint64_t {
	a := nhArms[h]
	var sum uint64
	for i := 0; i < int(n); i++ {
		sum += uint64(a.serve(a.next(i)))
		for _, v := range a.vals {
			sum += uint64(len(v))
			if len(v) > 0 {
				sum += uint64(v[0])
			}
		}
	}
	return C.uint64_t(sum)
}

// The null pass of rb_nh_pass: the same loop, the same request set per query and the same
// sink, around a call that is never inlined and reads only the path's length instead of the
// mux (nhNull). Its instructions per lookup are the loop's and the sink's, which H2 subtracts
// from rb_nh_pass's (hypotheses.md).
//
//export rb_nh_null_pass
func rb_nh_null_pass(h C.int, n C.size_t) C.uint64_t {
	a := nhArms[h]
	var sum uint64
	for i := 0; i < int(n); i++ {
		sum += uint64(a.nhNull(a.next(i)))
		for _, v := range a.vals {
			sum += uint64(len(v))
			if len(v) > 0 {
				sum += uint64(v[0])
			}
		}
	}
	return C.uint64_t(sum)
}

// nhNull stands for a.serve in the null pass: it reads the path's length, finds a route for
// every request, and captures nothing.
//
//go:noinline
func (a *nhArm) nhNull(r *http.Request) uint32 {
	a.vals = a.vals[:0]
	if r == nil {
		return 0xFFFFFFFF
	}
	return uint32(len(r.URL.Path) & 1)
}
