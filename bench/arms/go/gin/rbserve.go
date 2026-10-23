// Per-request lookup state for round 3's Go server (server/go/gin.go). gin's Engine keeps the
// params and skipped-nodes buffers in each Context it takes from its pool (gin.go, ServeHTTP and
// allocateContext), so concurrent requests never share them. RbEngine.Lookup (rbshim.go) keeps one
// set for the whole engine, which round 2's single-threaded harness needs and a server cannot
// share. LookupState is Lookup with the caller's buffers; rbshim.go and the files vendored from gin
// are unchanged.
package gin

// RbState is the lookup state of one request, sized as Prepare sizes the engine's.
type RbState struct {
	params       *Params
	skippedNodes *[]skippedNode
}

// NewState returns a state for one request at a time; call it after Prepare.
func (engine *RbEngine) NewState() *RbState {
	v := make(Params, 0, engine.maxParams)
	skippedNodes := make([]skippedNode, 0, engine.maxSections)
	return &RbState{params: &v, skippedNodes: &skippedNodes}
}

// LookupState is Lookup with st's buffers. The parameters stay valid until st's next lookup.
func (engine *RbEngine) LookupState(st *RbState, httpMethod, rPath string) (HandlersChain, Params) {
	*st.params = (*st.params)[:0]
	*st.skippedNodes = (*st.skippedNodes)[:0]
	t := engine.trees
	for i, tl := 0, len(t); i < tl; i++ {
		if t[i].method != httpMethod {
			continue
		}
		root := t[i].root
		value := root.getValue(rPath, st.params, st.skippedNodes, false)
		var params Params
		if value.params != nil {
			params = *value.params
		}
		return value.handlers, params
	}
	return nil, nil
}
