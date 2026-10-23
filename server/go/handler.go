// What every router's program answers. A hit is 200 text/plain. In measured mode the body is the
// fixed 13 bytes and the route id and every captured value are folded into a sink (round 2's rule
// for every timed loop, detail::fold in bench/core/runner.hpp: the id, then each value's length and
// first byte), so no router's capture work can be skipped. In check mode the body is the route id
// in decimal, then a tab and each value as the router returned it, then a newline. A miss is 404
// with no body.
//
// GET / and HEAD / are answered before any router is called, unless the routes file has "GET /":
// route id m (the number of routes) and no captured values, the readiness probe of lab/t1. The
// routers hold exactly the file's routes.
package main

import (
	"fmt"
	"net/http"
	"strconv"
)

// sink keeps the measured mode's fold alive. It is written by every request. With GOMAXPROCS(1)
// the only interleaving is preemption, and a lost update would not matter: the value is never read.
var sink uint64

var (
	textPlain = []string{"text/plain"}
	helloBody = []byte("Hello, World!")
)

// replier answers a request once a router has decided. A write error means the client is gone,
// and there is nothing to do about it, so it is dropped.
type replier struct {
	check bool
}

// hit answers a found route. vals are the captured values in pattern order.
func (p replier) hit(w http.ResponseWriter, id int, vals []string) {
	w.Header()["Content-Type"] = textPlain
	if !p.check {
		s := sink + uint64(id)
		for _, v := range vals {
			s += uint64(len(v))
			if len(v) > 0 {
				s += uint64(v[0])
			}
		}
		sink = s
		_, _ = w.Write(helloBody)
		return
	}
	body := strconv.AppendInt(make([]byte, 0, 64), int64(id), 10)
	for _, v := range vals {
		body = append(body, '\t')
		body = append(body, v...)
	}
	body = append(body, '\n')
	_, _ = w.Write(body)
}

// miss answers a path no route matches: 404 and an empty body. net/http then sends
// Content-Length: 0 and keeps the connection open.
func (p replier) miss(w http.ResponseWriter) {
	w.WriteHeader(http.StatusNotFound)
}

// probe wraps a router's handler. It answers the readiness probe, GET / and HEAD /, as route id
// with no values, and passes every other request to the router. One string comparison is its
// whole cost per request, the same for every router, including the null router.
type probe struct {
	next http.Handler
	rep  replier
	id   int
}

func (p probe) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/" && (r.Method == http.MethodGet || r.Method == http.MethodHead) {
		p.rep.hit(w, p.id, nil)
		return
	}
	p.next.ServeHTTP(w, r)
}

// guard runs fn and returns what it panicked with as an error. The routers panic when they
// cannot hold a table (round 2's adapters caught the same panics and reported a refusal).
func guard(fn func()) (err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("%v", r)
		}
	}()
	fn()
	return nil
}
