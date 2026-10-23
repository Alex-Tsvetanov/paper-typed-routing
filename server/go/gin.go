// gin-gonic/gin v1.12.0 in a server, used as its documentation shows: gin.New() in release mode
// (no Logger, no Recovery), engine.GET(pattern, handler) for each route, and the Engine itself as
// the server's http.Handler, so a request pays Engine.ServeHTTP's own steps: a pooled Context, the
// route tree search, then the handlers. Each handler closes over the route's id and reads the
// values from c.Params in pattern order. The module is the real one from the Go proxy, pinned by
// go.sum. Its tree.go is byte for byte the one round 2 vendored (bench/arms/go/gin/tree.go).
//
// NoRoute is c.AbortWithStatus(404): the status is written at once, so gin sends no body (its own
// 404 body is written only when nothing else was). The defaults stay on, and they decide the other
// answers:
//   - a path that differs from a route only by a trailing slash gets a 301
//     (RedirectTrailingSlash);
//   - a method other than GET reaches NoRoute, an empty 404 (HandleMethodNotAllowed is off by
//     default, so gin never answers 405).
//
// No request set holds such a path or method. GET / and HEAD / are answered before the engine
// (handler.go).
package main

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

func newGin(routes []route, rep replier) (http.Handler, error) {
	gin.SetMode(gin.ReleaseMode)
	e := gin.New()
	err := guard(func() {
		for id, r := range routes {
			e.GET(colonPattern(r), ginHandle(id, rep))
		}
	})
	if err != nil {
		return nil, err
	}
	e.NoRoute(func(c *gin.Context) { c.AbortWithStatus(http.StatusNotFound) })
	return e, nil
}

func ginHandle(id int, rep replier) gin.HandlerFunc {
	return func(c *gin.Context) {
		var vals [maxCaptures]string
		for i, p := range c.Params {
			vals[i] = p.Value
		}
		rep.hit(c.Writer, id, vals[:len(c.Params)])
	}
}
