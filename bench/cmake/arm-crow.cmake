FetchContent_Declare(rb_crow_src URL "https://codeload.github.com/CrowCpp/Crow/tar.gz/${RB_CROW_COMMIT}"
                     URL_HASH SHA256=${RB_CROW_SHA256} SOURCE_SUBDIR no-cmake)
FetchContent_Declare(rb_asio_src URL "https://codeload.github.com/chriskohlhoff/asio/tar.gz/${RB_ASIO_COMMIT}"
                     URL_HASH SHA256=${RB_ASIO_SHA256} SOURCE_SUBDIR no-cmake)
FetchContent_MakeAvailable(rb_crow_src rb_asio_src)
add_library(rb_crow INTERFACE)
target_include_directories(rb_crow SYSTEM INTERFACE "${rb_crow_src_SOURCE_DIR}/include"
                                                    "${rb_asio_src_SOURCE_DIR}/asio/include")
target_compile_definitions(rb_crow INTERFACE ASIO_STANDALONE)
find_package(Threads REQUIRED)
rb_arm(crow arms/crow.cpp rb_crow Threads::Threads)
