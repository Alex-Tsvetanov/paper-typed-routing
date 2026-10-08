set(PCRE2_BUILD_PCRE2GREP OFF CACHE BOOL "" FORCE)
set(PCRE2_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(PCRE2_BUILD_PCRE2_8 ON CACHE BOOL "" FORCE)
set(PCRE2_SUPPORT_JIT OFF CACHE BOOL "" FORCE)
set(PCRE2_STATIC_PIC ON CACHE BOOL "" FORCE)
FetchContent_Declare(rb_pcre2_src URL "${RB_PCRE2_URL}" URL_HASH SHA256=${RB_PCRE2_SHA256})
FetchContent_Declare(rb_r3_src URL "https://codeload.github.com/c9s/r3/tar.gz/${RB_R3_COMMIT}"
                     URL_HASH SHA256=${RB_R3_SHA256} SOURCE_SUBDIR no-cmake)
FetchContent_MakeAvailable(rb_pcre2_src rb_r3_src)
# r3's own CMake needs find_package(PCRE2) against an installed PCRE2, so its library is
# built here from the same source list its src/CMakeLists.txt names.
set(_r3 "${rb_r3_src_SOURCE_DIR}")
set(HAVE_STRDUP 1)
set(HAVE_STRNDUP 1)
set(HAVE_STDBOOL_H 1)
configure_file("${_r3}/config.h.cmake" "${CMAKE_CURRENT_BINARY_DIR}/r3-config/config.h")
add_library(rb_r3 STATIC "${_r3}/src/edge.c" "${_r3}/src/match_entry.c" "${_r3}/src/memory.c"
            "${_r3}/src/node.c" "${_r3}/src/slug.c" "${_r3}/src/str.c" "${_r3}/src/token.c")
target_compile_definitions(rb_r3 PRIVATE _GNU_SOURCE)
target_include_directories(rb_r3 PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/r3-config" "${_r3}/include" "${_r3}/src")
target_link_libraries(rb_r3 PUBLIC pcre2-8-static)
rb_arm(r3 arms/r3.cpp rb_r3)
# r3's include directory has a memory.h; searched after the system headers, it cannot shadow <memory.h>.
target_compile_options(arm_r3 PRIVATE "-idirafter${_r3}/include")
