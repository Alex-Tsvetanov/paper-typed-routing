module mserver-go

go 1.27

require (
	github.com/gin-gonic/gin v1.12.0
	github.com/go-chi/chi/v5 v5.3.2
	github.com/julienschmidt/httprouter v1.3.0
)

// Round 2's vendored trees (bench/arms/go), the same code its in-process arms timed: gin's
// route tree at v1.12.0 with a shim for the Engine parts a lookup uses, and chi's router at
// v5.3.2 with a shim for the part of Mux.routeHTTP that finds a route.
replace github.com/gin-gonic/gin => ../../bench/arms/go/gin

replace github.com/go-chi/chi/v5 => ../../bench/arms/go/chi
