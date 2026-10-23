// The null router: it answers route 0 with no values for every request and never reads the path.
// It is the floor of the server's own cost, with no router work in it. Only the readiness probe
// in front of it (handler.go) answers GET / otherwise, as route m.
package main

import "net/http"

type nullRouter struct {
	rep replier
}

func newNull(_ []route, rep replier) (http.Handler, error) {
	return nullRouter{rep: rep}, nil
}

func (n nullRouter) ServeHTTP(w http.ResponseWriter, _ *http.Request) {
	n.rep.hit(w, 0, nil)
}
