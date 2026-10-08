# gin's route tree through the Go arms' c-archive (cmake/ffi-go.cmake, arms/go/gin.go). The
# tree is vendored in arms/go/gin; each vendored file must hash as at the pinned tag
# (cmake/pins.cmake).
include(${CMAKE_CURRENT_LIST_DIR}/ffi-go.cmake)
foreach(_f tree.go internal/bytesconv/bytesconv.go)
    file(SHA256 "${RB_GO_MODULE}/gin/${_f}" _h)
    string(MAKE_C_IDENTIFIER "${_f}" _k)
    if(NOT _h STREQUAL RB_GIN_SHA256_${_k})
        message(FATAL_ERROR "arms/go/gin/${_f} differs from gin ${RB_GIN_TAG} (sha256 ${_h})")
    endif()
endforeach()
rb_go_arm(gin arms/gin.cpp)
