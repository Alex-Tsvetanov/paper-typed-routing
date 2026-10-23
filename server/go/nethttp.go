// net/http's ServeMux in a server, with the patterns of Go 1.22 and later, as round 2 uses it
// (bench/arms/go/nethttp.go): one ServeMux holds every route, each route has its own handler, and
// the handler reads its values with r.PathValue(name) in pattern order. Each handler closes over
// its route's id and answers the request itself, so the mux is the http.Handler of the server.
//
// A root route in the file is "GET /{$}": a pattern "GET /" would match every path. A catch-all
// "/" for every method answers a miss with an empty 404, since the mux's own answer has a text
// body. It is not a route and has no id. Every "GET /..." route is more specific than "/", so
// none conflicts with it.
//
// A path that is not canonical ("/a//b"), or that names a subtree without its trailing slash
// ("/f" when "/f/{p0...}" is registered), gets the mux's own redirect, not a 404. Round 2 counted
// those as misses. No request set holds such a path.
package main

import (
	"net/http"
	"strings"
)

// nhRoute is the handler of one route.
type nhRoute struct {
	id    int
	names []string // the route's capture names, in pattern order
	rep   replier
}

func (h *nhRoute) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	var vals [maxCaptures]string
	for i, name := range h.names {
		vals[i] = r.PathValue(name)
	}
	h.rep.hit(w, h.id, vals[:len(h.names)])
}

type nhMiss struct {
	rep replier
}

func (h nhMiss) ServeHTTP(w http.ResponseWriter, _ *http.Request) {
	h.rep.miss(w)
}

func newNetHTTP(routes []route, rep replier) (http.Handler, error) {
	mux := http.NewServeMux()
	err := guard(func() {
		for id, r := range routes {
			mux.Handle(nhPattern(r), &nhRoute{id: id, names: captureNames(r), rep: rep})
		}
		mux.Handle("/", nhMiss{rep: rep})
	})
	if err != nil {
		return nil, err
	}
	return mux, nil
}

func captureNames(r route) []string {
	names := make([]string, 0, r.captures())
	for _, s := range r {
		if s.kind != segLiteral {
			names = append(names, s.text)
		}
	}
	return names
}

// nhPattern converts a route to ServeMux's syntax: "GET /a/{p0}", and "{p1...}" for a catch-all.
// It is round 2's conversion (bench/arms/nethttp.cpp, NetHttpArm::add), with "GET /{$}" for the
// root.
func nhPattern(r route) string {
	if len(r) == 0 {
		return "GET /{$}"
	}
	var b strings.Builder
	b.WriteString("GET ")
	for _, s := range r {
		b.WriteByte('/')
		switch s.kind {
		case segLiteral:
			b.WriteString(s.text)
		case segParam:
			b.WriteString("{" + s.text + "}")
		case segRest:
			b.WriteString("{" + s.text + "...}")
		}
	}
	return b.String()
}
