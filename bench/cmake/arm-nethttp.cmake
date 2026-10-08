# net/http's ServeMux through the Go arms' c-archive (cmake/ffi-go.cmake, arms/go/nethttp.go).
# The router is the standard library of the Go toolchain, so the toolchain is its pin
# (RB_NETHTTP_GO, cmake/pins.cmake): a build with another Go version stops here.
include(${CMAKE_CURRENT_LIST_DIR}/ffi-go.cmake)
if(NOT RB_GO_TOOLCHAIN MATCHES "^go version ([^ ]+) " OR NOT CMAKE_MATCH_1 STREQUAL RB_NETHTTP_GO)
    message(FATAL_ERROR "the nethttp arm is pinned to ${RB_NETHTTP_GO}; ${RB_GO} reports '${RB_GO_TOOLCHAIN}'")
endif()
rb_go_arm(nethttp arms/nethttp.cpp)
target_compile_definitions(arm_nethttp PRIVATE RB_NETHTTP_GO="${RB_NETHTTP_GO}")
