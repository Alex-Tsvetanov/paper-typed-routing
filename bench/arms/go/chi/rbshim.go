// The part of chi's Mux.routeHTTP that finds a route, for rbench's chi arm (arms/go/chi.go).
// Everything else in this directory is go-chi/chi at tag v5.3.2 (commit
// 38939062c5df4d3e8814aad1a488983112627ced), byte for byte: chain.go, chi.go, context.go,
// mux.go and tree.go (the package's non-test sources; the middleware package is not used). Its
// licence text is bench/data/LICENSE-chi, the LICENSE at that commit. go.mod here is rbench's,
// so that the outer module can replace github.com/go-chi/chi/v5 with this directory.
//
// RbFind follows Mux.routeHTTP of that version for a request that reaches the Mux with a
// route context from the Mux's pool: the context reset (Mux.ServeHTTP resets a pooled
// context), the method looked up in methodMap, and the tree search (tree.FindRoute), which
// returns the endpoint's handler. routeHTTP then calls the handler; the arm does that itself.
// A method that has no route in the tree finds no handler, as routeHTTP's 405 and 404 paths
// do not call an endpoint.
package chi

import "net/http"

// RbFind resets rctx and searches mx's tree for method and path, as a request routed by mx
// would be; it returns the matched endpoint's handler, or nil.
func (mx *Mux) RbFind(rctx *Context, method, path string) http.Handler {
	rctx.Reset()
	m, ok := methodMap[method]
	if !ok {
		return nil
	}
	_, _, h := mx.tree.FindRoute(rctx, m, path)
	return h
}
