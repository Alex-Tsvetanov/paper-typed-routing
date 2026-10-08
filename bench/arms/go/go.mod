module rbgoarms

go 1.27

require (
	github.com/gin-gonic/gin v1.12.0
	github.com/go-chi/chi/v5 v5.3.2
	github.com/julienschmidt/httprouter v1.3.0
)

// gin's route tree, vendored at v1.12.0 with a shim for the Engine parts a lookup uses
// (gin/rbshim.go).
replace github.com/gin-gonic/gin => ./gin

// chi's router, vendored at v5.3.2 with a shim for the part of Mux.routeHTTP a lookup uses
// (chi/rbshim.go).
replace github.com/go-chi/chi/v5 => ./chi
