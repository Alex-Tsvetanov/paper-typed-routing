# regexmatcher-v2-goloop (design/review-runs/boundary-arms.md): RegexMatcher v2 called from a Go loop, one
# Go-to-C call per lookup, through the Go arms' c-archive (cmake/ffi-go.cmake, arms/go/v2loop.go). v2 is in a
# translation unit of its own (arms/capi/v2_goloop.cpp) beside the adapter's
# (arms/regexmatcher_v2_goloop.cpp); the Go loop calls it through a pointer the adapter hands it.
include(${CMAKE_CURRENT_LIST_DIR}/ffi-go.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/regexmatcher-v2.cmake)
rb_go_arm(regexmatcher-v2-goloop arms/regexmatcher_v2_goloop.cpp)
target_sources(arm_regexmatcher_v2_goloop PRIVATE arms/capi/v2_goloop.cpp)
target_link_libraries(arm_regexmatcher_v2_goloop PRIVATE RegexMatcher::route)
target_compile_definitions(arm_regexmatcher_v2_goloop PRIVATE RB_REGEXMATCHER_COMMIT="${RB_REGEXMATCHER_COMMIT}")
