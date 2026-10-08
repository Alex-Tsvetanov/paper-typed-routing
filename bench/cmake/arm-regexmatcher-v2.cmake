# RegexMatcher v2's table built at run time (cmake/regexmatcher-v2.cmake, arms/rm_arm.hpp).
include(${CMAKE_CURRENT_LIST_DIR}/regexmatcher-v2.cmake)
rb_arm(regexmatcher-v2 arms/regexmatcher_v2.cpp RegexMatcher::route)
target_compile_definitions(arm_regexmatcher_v2 PRIVATE RB_REGEXMATCHER_COMMIT="${RB_REGEXMATCHER_COMMIT}")
