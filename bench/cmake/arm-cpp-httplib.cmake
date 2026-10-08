# cpp-httplib, one header (httplib.h), without TLS or compression.
FetchContent_Declare(rb_httplib_src URL "https://codeload.github.com/yhirose/cpp-httplib/tar.gz/${RB_HTTPLIB_COMMIT}"
                     URL_HASH SHA256=${RB_HTTPLIB_SHA256} SOURCE_SUBDIR no-cmake)
FetchContent_MakeAvailable(rb_httplib_src)
find_package(Threads REQUIRED)
add_library(rb_httplib INTERFACE)
target_include_directories(rb_httplib SYSTEM INTERFACE "${rb_httplib_src_SOURCE_DIR}")
rb_arm(cpp-httplib arms/cpp_httplib.cpp rb_httplib Threads::Threads)
