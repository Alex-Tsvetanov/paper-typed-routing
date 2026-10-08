// The parts of gin's Engine that a lookup in gin's route tree uses, for rbench's gin arm
// (arms/go/gin.go). Everything else in this directory is gin-gonic/gin at tag v1.12.0
// (commit 73726dc606796a025971fe451f0aa6f1b9b847f6), byte for byte: tree.go and
// internal/bytesconv/bytesconv.go. tree.go carries Julien Schmidt's BSD-style notice (it
// derives from httprouter); its licence text is bench/data/LICENSE-httprouter, the LICENSE of
// julienschmidt/httprouter at commit 484018016424d215c0b87c42f4c9b57d980fbd00 (the same text
// as at v1.3.0). The rest of gin is under the MIT licence, text bench/data/LICENSE-gin (the
// LICENSE of gin at the commit above). go.mod here is rbench's, so that the outer module can
// replace github.com/gin-gonic/gin with this directory and tree.go keeps its import path of
// internal/bytesconv.
//
// Copied from gin v1.12.0, unchanged: HandlerFunc and HandlersChain (gin.go), assert1 and
// safeUint16 (utils.go). Context is an empty struct here: the tree only stores handlers.
// RbEngine follows gin.go and context.go of that version:
//   AddRoute  Engine.addRoute without its debug print (RouterGroup.handle joins the path with
//             the group's base path "/" first, which leaves an rbench pattern unchanged)
//   Prepare   Engine.allocateContext: params and skipped nodes sized to maxParams and
//             maxSections, once all routes are added, as for a Context of a serving Engine
//   Lookup    Context.reset, then the tree search of Engine.handleHTTPRequest in gin's
//             default configuration (UseRawPath, UseEscapedPath and RemoveExtraSlash off, so
//             unescape is false). Engine.ServeHTTP first rewrites escaped colons in the
//             trees (updateRouteTrees); no rbench pattern has one, so that step is left out.
package gin

import "math"

// HandlerFunc defines the handler used by gin middleware as return value.
type HandlerFunc func(*Context)

// HandlersChain defines a HandlerFunc slice.
type HandlersChain []HandlerFunc

// Context stands in for gin's request context, which the tree never reads.
type Context struct{}

func assert1(guard bool, text string) {
	if !guard {
		panic(text)
	}
}

// safeUint16 converts int to uint16 safely, capping at math.MaxUint16
func safeUint16(n int) uint16 {
	if n > math.MaxUint16 {
		return math.MaxUint16
	}
	return uint16(n)
}

// RbEngine holds the method trees and the lookup state of one gin Engine and its Context.
type RbEngine struct {
	trees        methodTrees
	maxParams    uint16
	maxSections  uint16
	params       *Params
	skippedNodes *[]skippedNode
}

// RbNew returns an engine with no routes; gin's New makes the trees the same way.
func RbNew() *RbEngine {
	return &RbEngine{trees: make(methodTrees, 0, 9)}
}

// AddRoute adds a route as Engine.addRoute does. It panics, as gin does, when the tree
// cannot hold the route.
func (engine *RbEngine) AddRoute(method, path string, handlers HandlersChain) {
	assert1(path[0] == '/', "path must begin with '/'")
	assert1(method != "", "HTTP method can not be empty")
	assert1(len(handlers) > 0, "there must be at least one handler")

	root := engine.trees.get(method)
	if root == nil {
		root = new(node)
		root.fullPath = "/"
		engine.trees = append(engine.trees, methodTree{method: method, root: root})
	}
	root.addRoute(path, handlers)

	if paramsCount := countParams(path); paramsCount > engine.maxParams {
		engine.maxParams = paramsCount
	}

	if sectionsCount := countSections(path); sectionsCount > engine.maxSections {
		engine.maxSections = sectionsCount
	}
}

// Prepare allocates the lookup state as Engine.allocateContext does.
func (engine *RbEngine) Prepare() {
	v := make(Params, 0, engine.maxParams)
	skippedNodes := make([]skippedNode, 0, engine.maxSections)
	engine.params = &v
	engine.skippedNodes = &skippedNodes
}

// Lookup returns the handlers and the parameters of a request, or nil handlers when the
// method's tree has no route for the path (gin would then answer a trailing-slash redirect
// or 404). The parameters stay valid until the next Lookup.
func (engine *RbEngine) Lookup(httpMethod, rPath string) (HandlersChain, Params) {
	*engine.params = (*engine.params)[:0]
	*engine.skippedNodes = (*engine.skippedNodes)[:0]
	t := engine.trees
	for i, tl := 0, len(t); i < tl; i++ {
		if t[i].method != httpMethod {
			continue
		}
		root := t[i].root
		value := root.getValue(rPath, engine.params, engine.skippedNodes, false)
		var params Params
		if value.params != nil {
			params = *value.params
		}
		return value.handlers, params
	}
	return nil, nil
}
