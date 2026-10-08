# httprouter through the Go arms' c-archive (cmake/ffi-go.cmake, arms/go/httprouter.go).
include(${CMAKE_CURRENT_LIST_DIR}/ffi-go.cmake)
rb_go_arm(httprouter arms/httprouter.cpp)
