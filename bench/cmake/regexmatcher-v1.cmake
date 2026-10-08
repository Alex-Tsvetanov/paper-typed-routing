# RegexMatcher v1, the regex-set engine at d16f30a8, as the INTERFACE target rb_regexmatcher_v1:
# for rbench's regexmatcher-v1 reference arm (cmake/arm-regexmatcher-v1.cmake) and the paper's
# server's v1 router arm (server/CMakeLists.txt), both behind arms/regexmatcher_v1_wrap.hpp.
# Fetched without running its CMake (SOURCE_SUBDIR no-cmake), so its targets cannot clash with
# v2's; the version header its CMake would generate is written here, into the build tree. Needs
# cmake/pins.cmake and FetchContent.
include_guard(GLOBAL)
FetchContent_Declare(rb_regexmatcher_v1_src
    URL "https://codeload.github.com/cpp-for-everything/RegexMatcher/tar.gz/${RB_REGEXMATCHER_COMMIT_V1}"
    URL_HASH SHA256=${RB_REGEXMATCHER_SHA256_V1} SOURCE_SUBDIR no-cmake)
FetchContent_MakeAvailable(rb_regexmatcher_v1_src)
set(_rm1_cfg "${CMAKE_CURRENT_BINARY_DIR}/rb-regexmatcher-v1")
file(WRITE "${_rm1_cfg}/RegexMatcherConfig.h.tmp"
     "// Written by cmake/regexmatcher-v1.cmake: the version of RegexMatcher d16f30a8.\n"
     "#define RegexMatcher_VERSION_MAJOR 2\n#define RegexMatcher_VERSION_MINOR 0\n"
     "#define RegexMatcher_VERSION_PATCH 0\n#define RegexMatcher_VERSION_TWEAK 1\n")
file(COPY_FILE "${_rm1_cfg}/RegexMatcherConfig.h.tmp" "${_rm1_cfg}/RegexMatcherConfig.h" ONLY_IF_DIFFERENT)
add_library(rb_regexmatcher_v1 INTERFACE)
target_include_directories(rb_regexmatcher_v1 SYSTEM INTERFACE "${rb_regexmatcher_v1_src_SOURCE_DIR}/include" "${_rm1_cfg}")
