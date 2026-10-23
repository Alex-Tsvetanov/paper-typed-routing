//go:build !windows && !(linux && p2v2cgo)

// No v2 library in this build: a Linux build without the tag p2v2cgo (so that CGO_ENABLED=0 builds
// of the other routers keep working), or another system. --router v2 exits 2 and says so.
package main

import "fmt"

type v2Table struct{}

func newV2Table([]string) (*v2Table, error) {
	return nil, fmt.Errorf("%w: this build has no p2v2 library (on Linux build with -tags p2v2cgo, see v2_cgo.go)",
		errV2Unavailable)
}

func (*v2Table) find(string, *[maxCaptures]string) (uint32, int) {
	return v2NoRoute, 0
}
