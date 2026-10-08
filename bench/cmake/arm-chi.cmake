# chi's Mux through the Go arms' c-archive (cmake/ffi-go.cmake, arms/go/chi.go). chi's sources
# are vendored in arms/go/chi; each vendored file must hash as at the pinned tag
# (cmake/pins.cmake).
include(${CMAKE_CURRENT_LIST_DIR}/ffi-go.cmake)
foreach(_f chain.go chi.go context.go mux.go tree.go)
    file(SHA256 "${RB_GO_MODULE}/chi/${_f}" _h)
    string(MAKE_C_IDENTIFIER "${_f}" _k)
    if(NOT _h STREQUAL RB_CHI_SHA256_${_k})
        message(FATAL_ERROR "arms/go/chi/${_f} differs from chi ${RB_CHI_TAG} (sha256 ${_h})")
    endif()
endforeach()
rb_go_arm(chi arms/chi.cpp)
