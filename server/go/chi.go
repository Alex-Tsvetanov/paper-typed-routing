// go-chi/chi v5.5.0 in a server, used as its documentation shows: chi.NewRouter(),
// mux.Get(pattern, handler) for each route, and the Mux itself as the server's http.Handler, so a
// request pays Mux.ServeHTTP's own steps: a pooled route context put into the request's context,
// the tree search, then the handler. Each handler closes over the route's id and reads the values
// with chi.RouteContext(r.Context()).URLParams.Values, in pattern order. The module is the real
// one from the Go proxy, pinned by go.sum. Round 2 used v5.3.2, vendored (bench/arms/go/chi), and
// its adapter called a RbFind shim. v5.5.0 differs from that copy only off the lookup path
// (Mux.ServeHTTP, routeHTTP, tree.go findRoute are the same code):
//   - tree.go: the loop of tailSort (node insertion) uses slices.Backward;
//   - mux.go: the pool's New returns any, and Mount panics on mounting a router onto itself;
//   - context.go: Context.Clone is new, and URLParam by key uses slices.Backward (not called here);
//   - chi.go: documentation comments.
//
// mux.NotFound is an empty 404. The defaults stay on, and they decide the other answers: a method
// other than GET (HEAD and OPTIONS included) on a path some GET route matches gets 405 with an
// Allow header and no body, and any other method on a path no route matches reaches NotFound, an
// empty 404. chi does not redirect a trailing slash. No request set holds such a path or method.
// GET / and HEAD / are answered before the mux (handler.go).
package main

import (
	"net/http"

	"github.com/go-chi/chi/v5"
)

func newChi(routes []route, rep replier) (http.Handler, error) {
	mux := chi.NewRouter()
	err := guard(func() {
		for id, r := range routes {
			mux.Get(chiPattern(r), chiHandle(id, rep))
		}
		mux.NotFound(func(w http.ResponseWriter, _ *http.Request) { rep.miss(w) })
	})
	if err != nil {
		return nil, err
	}
	return mux, nil
}

func chiHandle(id int, rep replier) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		rep.hit(w, id, chi.RouteContext(r.Context()).URLParams.Values)
	}
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
