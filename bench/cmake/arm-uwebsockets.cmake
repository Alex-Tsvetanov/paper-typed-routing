# uWebSockets' HttpRouter, header only (src/HttpRouter.h and src/MoveOnlyFunction.h); nothing of
# uWS's networking is compiled.
FetchContent_Declare(rb_uws_src URL "https://codeload.github.com/uNetworking/uWebSockets/tar.gz/${RB_UWS_COMMIT}"
                     URL_HASH SHA256=${RB_UWS_SHA256} SOURCE_SUBDIR no-cmake)
FetchContent_MakeAvailable(rb_uws_src)
add_library(rb_uws INTERFACE)
target_include_directories(rb_uws SYSTEM INTERFACE "${rb_uws_src_SOURCE_DIR}/src")
rb_arm(uwebsockets arms/uwebsockets.cpp rb_uws)
