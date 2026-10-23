// mserver-go hosts one Go router in an HTTP server for the end-to-end block of P2
// (design/round3/end-to-end.md, sections 5 and 6):
//
//	mserver-go --port P --workers 1 --routes FILE --router httprouter|gin|nethttp|chi|null [--check]
//
// It listens on 127.0.0.1:P with net/http, HTTP/1.1 keep-alive, one worker (GOMAXPROCS(1)) and no
// logging per request. The router holds the file's routes and nothing else. GET / and HEAD / are
// answered before the router is called, as route m (the number of routes) with no values, unless
// the file has "GET /", which is then routed like any route. SIGINT or SIGTERM (Ctrl-C or
// Ctrl-Break on Windows) stops the server and exits 0.
//
// Exit codes: 0 after a stop signal, 1 for a server failure, 2 for a bad argument or routes file,
// 3 when the router refuses the table.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"runtime/debug"
	"sort"
	"strings"
	"syscall"
	"time"
)

const shutdownGrace = 5 * time.Second

// builders maps a router's name to the function that builds its http.Handler over the routes.
var builders = map[string]func([]route, replier) (http.Handler, error){
	"httprouter": newHTTPRouter,
	"gin":        newGin,
	"nethttp":    newNetHTTP,
	"chi":        newChi,
	"null":       newNull,
}

func main() {
	os.Exit(run(os.Args[1:], os.Stderr))
}

func run(args []string, stderr io.Writer) int {
	fs := flag.NewFlagSet("mserver-go", flag.ContinueOnError)
	fs.SetOutput(stderr)
	port := fs.Int("port", 0, "TCP port on 127.0.0.1")
	workers := fs.Int("workers", 1, "worker count (only 1)")
	routesFile := fs.String("routes", "", "routes file, lines \"GET <pattern>\"")
	name := fs.String("router", "", "router: "+strings.Join(routerNames(), "|"))
	check := fs.Bool("check", false, "answer with the route id and the captured values")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	build, known := builders[*name]
	switch {
	case *workers != 1:
		fmt.Fprintf(stderr, "mserver-go: --workers %d: this program runs one worker\n", *workers)
		return 2
	case *port < 1 || *port > 65535:
		fmt.Fprintf(stderr, "mserver-go: --port %d: want 1 to 65535\n", *port)
		return 2
	case *routesFile == "":
		fmt.Fprintln(stderr, "mserver-go: --routes is required")
		return 2
	case !known:
		fmt.Fprintf(stderr, "mserver-go: --router %q: want %s\n", *name, strings.Join(routerNames(), "|"))
		return 2
	}
	fmt.Fprintf(stderr, "mserver-go: %s\n", buildLine())
	runtime.GOMAXPROCS(1)

	routes, err := readRoutes(*routesFile)
	if err != nil {
		fmt.Fprintf(stderr, "mserver-go: %s: %v\n", *routesFile, err)
		return 2
	}
	rep := replier{check: *check}
	handler, err := build(routes, rep)
	if err != nil {
		fmt.Fprintf(stderr, "mserver-go: %s refuses the table: %v\n", *name, err)
		return 3
	}
	if !hasRoot(routes) {
		handler = probe{next: handler, rep: rep, id: len(routes)}
	}

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

	// Listen only once the table is built: the system accepts connections into the backlog from
	// listen on, so "ready when it accepts" must come after the routes are in.
	ln, err := net.Listen("tcp4", fmt.Sprintf("127.0.0.1:%d", *port))
	if err != nil {
		fmt.Fprintf(stderr, "mserver-go: %v\n", err)
		return 1
	}
	srv := &http.Server{Handler: handler, ErrorLog: log.New(io.Discard, "", 0)}
	served := make(chan error, 1)
	go func() { served <- srv.Serve(ln) }()

	select {
	case <-stop:
		ctx, cancel := context.WithTimeout(context.Background(), shutdownGrace)
		defer cancel()
		if err := srv.Shutdown(ctx); err != nil {
			_ = srv.Close()
		}
		<-served // Serve returns http.ErrServerClosed once the shutdown has begun
		return 0
	case err := <-served:
		if errors.Is(err, http.ErrServerClosed) {
			return 0
		}
		fmt.Fprintf(stderr, "mserver-go: %v\n", err)
		return 1
	}
}

// buildLine names the Go version and the GOAMD64 level this binary was built with, so a log shows
// which build ran.
func buildLine() string {
	version, level := runtime.Version(), "n/a"
	if info, ok := debug.ReadBuildInfo(); ok {
		version = info.GoVersion
		for _, s := range info.Settings {
			if s.Key == "GOAMD64" {
				level = s.Value
			}
		}
	}
	return fmt.Sprintf("%s GOAMD64=%s", version, level)
}

func routerNames() []string {
	names := make([]string, 0, len(builders))
	for n := range builders {
		names = append(names, n)
	}
	sort.Strings(names)
	return names
}
