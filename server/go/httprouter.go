// julienschmidt/httprouter v1.3.0 in a server, called as round 2 calls it (bench/arms/go/
// httprouter.go, rb_hr_lookup): one Router holds the routes and Router.Lookup finds one. Each
// route's own Handle, which closes over the route's id, answers the request with the values in
// the Params the lookup returned. Round 2's Handle wrote the id into a shared field instead,
// which two connections' goroutines could interleave.
package main

import (
	"net/http"
	"strings"

	"github.com/julienschmidt/httprouter"
)

type httpRouter struct {
	rt  *httprouter.Router
	rep replier
}

func newHTTPRouter(routes []route, rep replier) (http.Handler, error) {
	rt := httprouter.New()
	err := guard(func() {
		for id, r := range routes {
			rt.Handle(http.MethodGet, colonPattern(r), httpRouterHandle(id, rep))
		}
	})
	if err != nil {
		return nil, err
	}
	return &httpRouter{rt: rt, rep: rep}, nil
}

func httpRouterHandle(id int, rep replier) httprouter.Handle {
	return func(w http.ResponseWriter, _ *http.Request, ps httprouter.Params) {
		var vals [maxCaptures]string
		for i, p := range ps {
			vals[i] = p.Value
		}
		rep.hit(w, id, vals[:len(ps)])
	}
}

func (h *httpRouter) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// The path is r.URL.Path, as Router.ServeHTTP reads it. A miss, a trailing-slash hint (the
	// third result) and a method with no routes are all a 404 here, as in round 2.
	handle, ps, _ := h.rt.Lookup(r.Method, r.URL.Path)
	if handle == nil {
		h.rep.miss(w)
		return
	}
	handle(w, r, ps)
}

// colonPattern converts a route to the syntax of httprouter and gin: ":name" for a parameter
// and "*name" for a catch-all. It is round 2's conversion for both (bench/arms/httprouter.cpp,
// HttpRouterArm::add, and bench/arms/gin.cpp, GinArm::add), with "/" for the root.
func colonPattern(r route) string {
	var b strings.Builder
	for _, s := range r {
		b.WriteByte('/')
		switch s.kind {
		case segParam:
			b.WriteByte(':')
		case segRest:
			b.WriteByte('*')
		}
		b.WriteString(s.text)
	}
	if b.Len() == 0 {
		return "/"
	}
	return b.String()
}
