// go-chi/chi v5.3.2's router in a server, called as round 2 calls it (bench/arms/go/chi.go,
// chiArm.lookup, and bench/arms/go/chi/rbshim.go): one Mux holds the routes, and Mux.RbFind
// resets a route context, searches the tree and returns the endpoint's handler. The values are in
// the context's URLParams.
//
// Round 2 used one context and one shared id. A server runs a goroutine per connection, so each
// request takes a context from a pool, as chi's own Mux.ServeHTTP does. The endpoint handler is
// not called: it carries the route's id, and the adapter reads the id from the handler RbFind
// returned. Round 2 called the handler to record the id in a shared field.
package main

import (
	"net/http"
	"sync"

	"github.com/go-chi/chi/v5"
)

// chiRoute is the endpoint handler of one route. chi's Mux.Method needs an http.Handler. Nothing
// calls it.
type chiRoute struct {
	id int
}

func (*chiRoute) ServeHTTP(http.ResponseWriter, *http.Request) {}

type chiRouter struct {
	mux  *chi.Mux
	pool sync.Pool // of *chi.Context
	rep  replier
}

func newChi(routes []route, rep replier) (http.Handler, error) {
	c := &chiRouter{mux: chi.NewRouter(), rep: rep}
	c.pool.New = func() any { return chi.NewRouteContext() }
	err := guard(func() {
		for id, r := range routes {
			c.mux.Method(http.MethodGet, chiPattern(r), &chiRoute{id: id})
		}
	})
	if err != nil {
		return nil, err
	}
	return c, nil
}

func (c *chiRouter) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// The path is RawPath when set, else Path, as Mux.routeHTTP reads it. A method with no
	// routes finds no handler. A miss (chi would answer 404 or 405 itself) is a 404 here.
	path := r.URL.RawPath
	if path == "" {
		path = r.URL.Path
	}
	rctx := c.pool.Get().(*chi.Context)
	route, ok := c.mux.RbFind(rctx, r.Method, path).(*chiRoute)
	if !ok {
		c.pool.Put(rctx)
		c.rep.miss(w)
		return
	}
	c.rep.hit(w, route.id, rctx.URLParams.Values)
	c.pool.Put(rctx)
}

// chiPattern converts a route to chi's syntax: "{name}" for a parameter and "*" for a catch-all,
// whose value chi keeps under the key "*". It is round 2's conversion (bench/arms/chi.cpp,
// ChiArm::add), with "/" for the root.
func chiPattern(r route) string {
	out := make([]byte, 0, 64)
	for _, s := range r {
		out = append(out, '/')
		switch s.kind {
		case segLiteral:
			out = append(out, s.text...)
		case segParam:
			out = append(out, '{')
			out = append(out, s.text...)
			out = append(out, '}')
		case segRest:
			out = append(out, '*')
		}
	}
	if len(out) == 0 {
		return "/"
	}
	return string(out)
}
