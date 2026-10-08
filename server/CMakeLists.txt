# The paper's minimal HTTP/1.1 server (design/round2/minimal-server.md): one binary, three router
# arms, epoll. Built from the paper's root CMakeLists.txt (add_subdirectory(server)), or on its own
# for its unit tests (cmake -S server).
cmake_minimum_required(VERSION 3.25)
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(mserver LANGUAGES CXX)
    set(CMAKE_CXX_STANDARD 23)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)
    set(CMAKE_CXX_EXTENSIONS OFF)
    enable_testing()
endif()

# The instruction set (bench/cmake/isa.cmake; the root project includes it first, include_guard
# makes this a no-op there): src/route.hpp and src/arm_v1.hpp include its rb_isa.h.
include("${CMAKE_CURRENT_SOURCE_DIR}/../bench/cmake/isa.cmake")

# RegexMatcher v2 (its route matcher's Match is the router interface's result): from a checkout
# until v2 is public, as rbench takes it (bench/cmake/regexmatcher-v2.cmake).
if(NOT TARGET RegexMatcher::route)
    set(REGEXMATCHER_DIR "" CACHE PATH "RegexMatcher v2 source checkout (until v2 is public)")
    if(NOT REGEXMATCHER_DIR)
        message(FATAL_ERROR "the server needs REGEXMATCHER_DIR (v2 has no public release to pin yet)")
    endif()
    add_subdirectory("${REGEXMATCHER_DIR}" regexmatcher EXCLUDE_FROM_ALL)
endif()

# The HTTP/1.1 layer: parsing and the responses (no I/O, no router).
add_library(mserver_http1 STATIC src/http1.cpp)
target_include_directories(mserver_http1 PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/src")
target_link_libraries(mserver_http1 PUBLIC RegexMatcher::route)
target_compile_options(mserver_http1 PRIVATE -Wall -Wextra)

# The I/O loop: epoll, one thread.
add_library(mserver_loop STATIC src/loop.cpp)
target_link_libraries(mserver_loop PUBLIC mserver_http1)
target_compile_options(mserver_loop PRIVATE -Wall -Wextra)

add_executable(test_loopback tests/test_loopback.cpp)
target_link_libraries(test_loopback PRIVATE mserver_loop)
target_compile_options(test_loopback PRIVATE -Wall -Wextra)
add_test(NAME loopback COMMAND test_loopback)

# The v1 arm: RegexMatcher's engine at d16f30a8 (pinned, bench/cmake/pins.cmake), fetched as
# rbench fetches it, behind rbench's wrapper; its own library, so that its translation unit sees
# v1's include directory and not v2's (both have a matcher/core.hpp).
if(NOT TARGET rb_regexmatcher_v1)
    include(FetchContent)
    include("${CMAKE_CURRENT_SOURCE_DIR}/../bench/cmake/pins.cmake")
    include("${CMAKE_CURRENT_SOURCE_DIR}/../bench/cmake/regexmatcher-v1.cmake")
endif()
add_library(mserver_v1 STATIC src/arm_v1.cpp)
target_include_directories(mserver_v1 PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../bench")
target_link_libraries(mserver_v1 PRIVATE rb_regexmatcher_v1)

# The router arms, and the server.
add_library(mserver_arms STATIC src/arms.cpp)
target_link_libraries(mserver_arms PUBLIC mserver_http1 PRIVATE mserver_v1)
target_compile_options(mserver_arms PRIVATE -Wall -Wextra)
add_executable(mserver src/main.cpp)
target_link_libraries(mserver PRIVATE mserver_loop mserver_arms)
target_compile_options(mserver PRIVATE -Wall -Wextra)

# The arms' agreement on H6's tables needs t1/h6_targets, which the paper's root project builds.
add_executable(test_agreement tests/test_agreement.cpp)
target_link_libraries(test_agreement PRIVATE mserver_arms)
target_compile_options(test_agreement PRIVATE -Wall -Wextra)
if(TARGET h6_targets)
    add_test(NAME h6_agreement COMMAND "${CMAKE_COMMAND}" "-DH6_TARGETS=$<TARGET_FILE:h6_targets>"
             "-DAGREE=$<TARGET_FILE:test_agreement>" "-DOUT=${CMAKE_CURRENT_BINARY_DIR}/h6-agreement"
             -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/h6_agreement.cmake")
endif()

add_executable(test_contract tests/test_contract.cpp)
target_compile_options(test_contract PRIVATE -Wall -Wextra)
add_test(NAME contract COMMAND test_contract $<TARGET_FILE:mserver>)

add_executable(test_http1 tests/test_http1.cpp)
target_link_libraries(test_http1 PRIVATE mserver_http1)
target_compile_options(test_http1 PRIVATE -Wall -Wextra)
add_test(NAME http1 COMMAND test_http1)
