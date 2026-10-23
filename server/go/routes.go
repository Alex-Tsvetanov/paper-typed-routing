// The routes file and the pattern model. A line is "GET <pattern>" in rbench's syntax: "{p0}"
// stands for one segment and "{*p0}" for the rest of the path (bench/core/route.hpp, Seg::Param
// and Seg::Rest). Route i is line i. Each router file converts a route to its own syntax.
package main

import (
	"fmt"
	"os"
	"strings"
)

// maxCaptures is rbench's kMaxParams (bench/core/route.hpp): the most values one route captures.
const maxCaptures = 8

type segKind uint8

const (
	segLiteral segKind = iota
	segParam
	segRest
)

type segment struct {
	kind segKind
	text string // the literal, or the capture's name
}

// route is one GET route. The root path "/" has no segments.
type route []segment

// captures returns the number of values the route captures.
func (r route) captures() int {
	n := 0
	for _, s := range r {
		if s.kind != segLiteral {
			n++
		}
	}
	return n
}

// readRoutes reads the routes file.
func readRoutes(path string) ([]route, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return parseRoutes(string(data))
}

// parseRoutes reads "GET <pattern>" lines. A CR before the newline is dropped and an empty line
// is skipped. Any other line is an error.
func parseRoutes(text string) ([]route, error) {
	var routes []route
	for n, line := range strings.Split(text, "\n") {
		line = strings.TrimSuffix(line, "\r")
		if line == "" {
			continue
		}
		pattern, ok := strings.CutPrefix(line, "GET ")
		if !ok {
			return nil, fmt.Errorf("line %d: want \"GET <pattern>\", got %q", n+1, line)
		}
		r, err := parsePattern(pattern)
		if err != nil {
			return nil, fmt.Errorf("line %d: %w", n+1, err)
		}
		routes = append(routes, r)
	}
	return routes, nil
}

func parsePattern(p string) (route, error) {
	if !strings.HasPrefix(p, "/") {
		return nil, fmt.Errorf("pattern %q does not start with '/'", p)
	}
	if p == "/" {
		return route{}, nil
	}
	parts := strings.Split(p[1:], "/")
	r := make(route, 0, len(parts))
	for i, part := range parts {
		s, err := parseSegment(part)
		if err != nil {
			return nil, fmt.Errorf("pattern %q: %w", p, err)
		}
		if s.kind == segRest && i != len(parts)-1 {
			return nil, fmt.Errorf("pattern %q: a rest capture must be the last segment", p)
		}
		r = append(r, s)
	}
	if r.captures() > maxCaptures {
		return nil, fmt.Errorf("pattern %q: more than %d captures", p, maxCaptures)
	}
	return r, nil
}

func parseSegment(s string) (segment, error) {
	switch {
	case s == "":
		return segment{}, fmt.Errorf("empty segment")
	case len(s) >= 2 && s[0] == '{' && s[len(s)-1] == '}':
		name := s[1 : len(s)-1]
		kind := segParam
		if rest, ok := strings.CutPrefix(name, "*"); ok {
			kind, name = segRest, rest
		}
		if !validName(name) {
			return segment{}, fmt.Errorf("bad capture name in %q", s)
		}
		return segment{kind, name}, nil
	case strings.ContainsAny(s, "{}:* \t"):
		// Characters a router would read as syntax, or that cannot be in a request target.
		return segment{}, fmt.Errorf("bad literal segment %q", s)
	}
	return segment{segLiteral, s}, nil
}

func validName(name string) bool {
	if name == "" {
		return false
	}
	for _, c := range name {
		ok := c == '_' || (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
		if !ok {
			return false
		}
	}
	return true
}

// hasRoot reports whether the routes include the root path "/".
func hasRoot(routes []route) bool {
	for _, r := range routes {
		if len(r) == 0 {
			return true
		}
	}
	return false
}
