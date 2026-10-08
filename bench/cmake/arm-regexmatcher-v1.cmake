# RegexMatcher v1, the regex-set engine at d16f30a8, for the regexmatcher-v1 reference arm
# (arms/regexmatcher_v1.cpp, behind arms/regexmatcher_v1_wrap.hpp); the fetch is
# cmake/regexmatcher-v1.cmake.
include("${CMAKE_CURRENT_LIST_DIR}/regexmatcher-v1.cmake")
rb_arm(regexmatcher-v1 arms/regexmatcher_v1.cpp rb_regexmatcher_v1)
