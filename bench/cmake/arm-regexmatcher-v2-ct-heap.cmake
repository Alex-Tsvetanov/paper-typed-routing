# RegexMatcher v2's compile-time table copied into a heap block (arms/regexmatcher_v2_ct_heap.cpp):
# an exploratory arm, built only when RB_ARMS names it (RB_OPT_IN_ARMS). It reads the registry of
# the regexmatcher-v2-ct arm's tables and calls the lookup the regexmatcher-v2 arm defines.
include(${CMAKE_CURRENT_LIST_DIR}/regexmatcher-v2.cmake)
if(NOT "regexmatcher-v2-ct" IN_LIST RB_ARMS)
    message(FATAL_ERROR "regexmatcher-v2-ct-heap needs regexmatcher-v2-ct in RB_ARMS (its tables and their registry)")
endif()
rb_arm(regexmatcher-v2-ct-heap arms/regexmatcher_v2_ct_heap.cpp RegexMatcher::route)
target_compile_definitions(arm_regexmatcher_v2_ct_heap PRIVATE RB_REGEXMATCHER_COMMIT="${RB_REGEXMATCHER_COMMIT}")
