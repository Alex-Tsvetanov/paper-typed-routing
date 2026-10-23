// RegexMatcher v2 in the Go program, behind the C interface of server/capi/p2v2.h. It is the C++
// server's build of v2 (the same compiler, flags and table code as the server's v2 arm), so this
// arm is a same-server contrast: only the language boundary differs, and its cost goes to v2.
//
// The call mechanism differs between the two systems. On Linux it is cgo, a call into the static
// library libp2v2_c.a (v2_cgo.go, behind the build tag p2v2cgo). On Windows it is a call into the
// DLL p2v2.dll through syscall.SyscallN, without cgo (v2_windows.go). Each costs what its mechanism
// costs per request, and that cost is v2's. A build for any other system, or a Linux build without
// the tag, has no library: v2_none.go, and --router v2 exits 2. When the library is there, the
// program prints at start where it came from and how it was built (p2v2_build_info).
//
// newV2 gives p2v2_build the patterns of the routes file, route i being line i. It writes each
// parsed route back with rbenchPattern (rbench's syntax: "{p0}", "{*p0}"). For every pattern the
// parser accepts that is the identity, so the library gets the file's own text, with no
// conversion. A lookup passes the request's path, r.URL.Path, and gets the route id and the
// captured values as (offset, length) pairs into that path, which are sliced into strings here.
//
// The table holds GET routes only. This arm answers HEAD and every other method that is not GET
// with 404 (the other routers answer by their libraries' defaults, see their files). GET / and
// HEAD / are answered before the router (handler.go).
package main

import (
	"errors"
	"fmt"
	"net/http"
	"strings"
)

// v2NoRoute is P2V2_NO_ROUTE in p2v2.h.
const v2NoRoute = 0xFFFFFFFF

// errV2Unavailable marks a program without the v2 library, or one that cannot load it. It is a
// usage error (exit 2), not a refusal of the table (exit 3).
var errV2Unavailable = errors.New("router v2 is unavailable")

// A platform file defines v2Table and these:
//
//	newV2Table(patterns []string) (*v2Table, error)
//	(*v2Table).find(path string, vals *[maxCaptures]string) (id uint32, n int)
//	(*v2Table).describe() string
//
// find looks the path up as method 0 (GET), writes the n captured values into vals and returns the
// route id, or v2NoRoute. describe returns "v2 library <path or linked>: <build info>". newV2Table
// returns an error wrapping errV2Unavailable when the library is missing or lacks an entry point,
// and the library's own message when p2v2_build returns NULL.

type v2Router struct {
	table *v2Table
	rep   replier
}

func newV2(routes []route, rep replier) (http.Handler, error) {
	patterns := make([]string, len(routes))
	for i, r := range routes {
		patterns[i] = rbenchPattern(r)
	}
	t, err := newV2Table(patterns)
	if err != nil {
		return nil, err
	}
	return &v2Router{table: t, rep: rep}, nil
}

// describe is what main prints at start, after the table is built.
func (v *v2Router) describe() string { return v.table.describe() }

func (v *v2Router) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		v.rep.miss(w)
		return
	}
	var vals [maxCaptures]string
	id, n := v.table.find(r.URL.Path, &vals)
	if id == v2NoRoute {
		v.rep.miss(w)
		return
	}
	v.rep.hit(w, int(id), vals[:n])
}

// rbenchPattern writes a route in rbench's syntax, which is how the routes file has it: "{p0}" for
// a parameter and "{*p0}" for the rest of the path.
func rbenchPattern(r route) string {
	if len(r) == 0 {
		return "/"
	}
	var b strings.Builder
	for _, s := range r {
		b.WriteByte('/')
		switch s.kind {
		case segLiteral:
			b.WriteString(s.text)
		case segParam:
			b.WriteString("{" + s.text + "}")
		case segRest:
			b.WriteString("{*" + s.text + "}")
		}
	}
	return b.String()
}

// sliceCaptures turns n (offset, length) pairs into the values they name in path. It panics when
// the library reports a pair outside the path, which a correct build never does.
func sliceCaptures(path string, caps *[2 * maxCaptures]uint32, n uint32, vals *[maxCaptures]string) int {
	if n > maxCaptures {
		n = maxCaptures
	}
	for i := uint32(0); i < n; i++ {
		off, length := caps[2*i], caps[2*i+1]
		vals[i] = path[off : off+length]
	}
	return int(n)
}

// v2Failure is the error for a NULL from p2v2_build, with the library's message.
func v2Failure(message string) error {
	return fmt.Errorf("p2v2_build: %s", message)
}

// v2Description is the line main prints for the library: where it came from, and p2v2_build_info.
func v2Description(source, info string) string {
	return fmt.Sprintf("v2 library %s: %s", source, info)
}
