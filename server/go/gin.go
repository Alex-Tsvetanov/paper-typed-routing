// gin-gonic/gin v1.12.0's route tree in a server, called as gin's Engine calls it
// (gin.go, ServeHTTP and handleHTTPRequest; round 2's bench/arms/go/gin.go and
// bench/arms/go/gin/rbshim.go): gin.RbNew, AddRoute for each route, Prepare once, then per request
// a lookup with that request's own state from a sync.Pool, as the Engine takes a Context from its
// pool (bench/arms/go/gin/rbserve.go), then the route's handlers as Context.Next runs them.
//
// The route id is the position of the route's handler chain: every route's chain is a one-element
// slice of one backing array, which addRoute stores as given, so the chain the tree returns says
// which route matched. No state is shared between requests, and nothing is locked.
package main

import (
	"net/http"
	"sync"
	"unsafe"

	"github.com/gin-gonic/gin"
)

type ginRouter struct {
	eng    *gin.RbEngine
	chains gin.HandlersChain // route i's chain is chains[i : i+1 : i+1]
	pool   sync.Pool
	rep    replier
}

func newGin(routes []route, rep replier) (http.Handler, error) {
	g := &ginRouter{eng: gin.RbNew(), rep: rep, chains: make(gin.HandlersChain, len(routes))}
	nop := func(*gin.Context) {}
	err := guard(func() {
		for id, r := range routes {
			g.chains[id] = nop
			g.eng.AddRoute(http.MethodGet, colonPattern(r), g.chains[id:id+1:id+1])
		}
		g.eng.Prepare()
	})
	if err != nil {
		return nil, err
	}
	g.pool.New = func() any { return g.eng.NewState() }
	return g, nil
}

// routeOf is the id of the route whose chain the tree returned.
func (g *ginRouter) routeOf(handlers gin.HandlersChain) int {
	base := uintptr(unsafe.Pointer(unsafe.SliceData(g.chains)))
	at := uintptr(unsafe.Pointer(unsafe.SliceData(handlers)))
	return int((at - base) / unsafe.Sizeof(g.chains[0]))
}

func (g *ginRouter) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// The path is r.URL.Path, as Engine.handleHTTPRequest reads it with UseRawPath and
	// RemoveExtraSlash off. A miss (gin would answer a trailing-slash redirect or 404) is a 404.
	st := g.pool.Get().(*gin.RbState)
	handlers, ps := g.eng.LookupState(st, r.Method, r.URL.Path)
	if handlers == nil {
		g.pool.Put(st)
		g.rep.miss(w)
		return
	}
	for _, handle := range handlers {
		handle(nil)
	}
	id := g.routeOf(handlers)
	var vals [maxCaptures]string
	n := 0
	for _, p := range ps {
		if n < maxCaptures {
			vals[n] = p.Value
			n++
		}
	}
	g.pool.Put(st)
	g.rep.hit(w, id, vals[:n])
}
