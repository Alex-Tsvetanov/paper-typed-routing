// julienschmidt/httprouter v1.3.0 in a server, used as its documentation shows: httprouter.New()
// with its defaults, router.GET(pattern, handle) for each route, and the Router itself as the
// server's http.Handler, so a request pays Router.ServeHTTP's own steps. Each route's Handle
// closes over the route's id and answers the request with the values in the Params it was given.
// Round 2's adapter called Router.Lookup and a Handle that wrote the id into a shared field.
//
// Router.NotFound is an empty 404. The defaults stay on, and they decide the other answers:
//   - a path that differs from a route only by a trailing slash, or by case, gets a 301
//     (RedirectTrailingSlash, RedirectFixedPath);
//   - a method other than GET (HEAD included) on a path some GET route matches gets 405 with an
//     Allow header and a text body (HandleMethodNotAllowed), except OPTIONS, which gets 200 with
//     an Allow header and no body (HandleOPTIONS);
//   - any other method on a path no route matches reaches NotFound, an empty 404.
//
// No request set holds such a path or method. GET / and HEAD / are answered before the router
// (handler.go).
package main

import (
	"net/http"
	"strings"

	"github.com/julienschmidt/httprouter"
)

func newHTTPRouter(routes []route, rep replier) (http.Handler, error) {
	rt := httprouter.New()
	rt.NotFound = http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { rep.miss(w) })
	err := guard(func() {
		for id, r := range routes {
			rt.GET(colonPattern(r), httpRouterHandle(id, rep))
		}
	})
	if err != nil {
		return nil, err
	}
	return rt, nil
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
