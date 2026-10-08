# glaze's route table, header only (include/glaze/net/http_router.hpp); glaze's CMake is not run.
FetchContent_Declare(rb_glaze_src URL "https://codeload.github.com/stephenberry/glaze/tar.gz/${RB_GLAZE_COMMIT}"
                     URL_HASH SHA256=${RB_GLAZE_SHA256} SOURCE_SUBDIR no-cmake)
FetchContent_MakeAvailable(rb_glaze_src)
add_library(rb_glaze INTERFACE)
target_include_directories(rb_glaze SYSTEM INTERFACE "${rb_glaze_src_SOURCE_DIR}/include")
rb_arm(glaze arms/glaze.cpp rb_glaze)
