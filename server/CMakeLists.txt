# The paper's minimal HTTP/1.1 server (design/round2/minimal-server.md; round 3:
# design/round3/end-to-end.md): one binary, the router chosen at start. Linux: epoll, clang. Windows:
# an I/O completion port, MSVC. Built from the paper's root CMakeLists.txt (add_subdirectory(server)),
# or on its own for its unit tests (cmake -S server).
#
#   -DMSERVER_EXTERNALS=a;b;...   the external router arms (round 2's rbench adapters, compiled
#                                 unchanged; default: every one this platform builds)
cmake_minimum_required(VERSION 3.25)
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(mserver LANGUAGES C CXX)
    set(CMAKE_CXX_STANDARD 23)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)
    set(CMAKE_CXX_EXTENSIONS OFF)
    enable_testing()
endif()
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()
set(_bench "${CMAKE_CURRENT_SOURCE_DIR}/../bench")

if(MSVC)
    # The standard's preprocessor and __cplusplus, UTF-8 sources, conforming mode: glaze and Crow
    # test __cplusplus, and several arms' headers need the conforming preprocessor.
    add_compile_options(/Zc:__cplusplus /Zc:preprocessor /utf-8 /permissive- /EHsc)
    add_compile_definitions(_WIN32_WINNT=0x0A00 WIN32_LEAN_AND_MEAN NOMINMAX)
    set(_warn /W3)
else()
    set(_warn -Wall -Wextra)
endif()

# The instruction set (bench/cmake/isa.cmake; the root project includes it first, include_guard
# makes this a no-op there): src/route.hpp and src/arm_v1.hpp include its rb_isa.h.
include("${_bench}/cmake/isa.cmake")

include(FetchContent)
include("${_bench}/cmake/pins.cmake")
find_package(Git QUIET)
if(NOT COMMAND rb_git)
    function(rb_git dir out)
        execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${dir}" rev-parse HEAD
                        OUTPUT_VARIABLE _c OUTPUT_STRIP_TRAILING_WHITESPACE RESULT_VARIABLE _rc ERROR_QUIET)
        if(NOT _rc EQUAL 0)
            set(_c "unknown")
        endif()
        set(${out} "${_c}" PARENT_SCOPE)
    endfunction()
endif()

# RegexMatcher v2 (its route matcher's Match is the router interface's result), as rbench takes it
# (bench/cmake/regexmatcher-v2.cmake): the public release 2.1.0.0, fetched at its pinned commit and
# checked by sha256 (bench/cmake/pins.cmake), or a checkout given as REGEXMATCHER_DIR.
if(NOT TARGET RegexMatcher::route)
    include("${_bench}/cmake/regexmatcher-v2.cmake")
endif()

# The HTTP/1.1 layer: parsing and the responses (no I/O, no router).
add_library(mserver_http1 STATIC src/http1.cpp)
target_include_directories(mserver_http1 PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/src")
target_link_libraries(mserver_http1 PUBLIC RegexMatcher::route)
target_compile_options(mserver_http1 PRIVATE ${_warn})

# The I/O loop, one thread: epoll on Linux, an I/O completion port on Windows.
if(WIN32)
    add_library(mserver_loop STATIC src/loop_iocp.cpp)
    target_link_libraries(mserver_loop PUBLIC mserver_http1 ws2_32)
else()
    add_library(mserver_loop STATIC src/loop.cpp)
    target_link_libraries(mserver_loop PUBLIC mserver_http1)
endif()
target_compile_options(mserver_loop PRIVATE ${_warn})

# The v1 arm (Linux): RegexMatcher's engine at d16f30a8 (pinned, bench/cmake/pins.cmake), fetched as
# rbench fetches it, behind rbench's wrapper; its own library, so that its translation unit sees
# v1's include directory and not v2's (both have a matcher/core.hpp). Round 3 does not compare v1.
set(MSERVER_WITH_V1 OFF)
if(NOT WIN32)
    set(MSERVER_WITH_V1 ON)
    if(NOT TARGET rb_regexmatcher_v1)
        include("${_bench}/cmake/regexmatcher-v1.cmake")
    endif()
    add_library(mserver_v1 STATIC src/arm_v1.cpp)
    target_include_directories(mserver_v1 PRIVATE "${_bench}")
    target_link_libraries(mserver_v1 PRIVATE rb_regexmatcher_v1)
endif()

# The external arms (design/round3/end-to-end.md, section 6): round 2's adapters in bench/arms,
# compiled unchanged with src/shim ahead of bench/ on the include path, so that their
# "core/runner.hpp" is the shim's and RB_ARM registers them with the server (src/external.hpp).
# Each arm is fetched and configured by its own bench/cmake/arm-<name>.cmake, which calls rb_arm.
set(RB_SANITIZER "${P2_SANITIZER}")
set(_externals_all crow drogon oatpp pistache boost-url r3 uwebsockets glaze cpp-httplib)
find_package(Boost 1.92.0 EXACT QUIET CONFIG)
set(_externals_default ${_externals_all})
if(WIN32)
    # r3 at 83d362f includes POSIX headers (src/node.c: netinet/in.h). Pistache v0.4.26's CMake
    # build gives cl GCC's warning flags; its Windows build is its meson build with libevent
    # (design/round3/router-survey.md). Both are absent from the Windows cells for these reasons.
    list(REMOVE_ITEM _externals_default r3 pistache)
    message(STATUS "mserver: Windows, so no r3 and no pistache arm")
endif()
if(NOT Boost_FOUND)
    list(REMOVE_ITEM _externals_default boost-url)
    message(STATUS "mserver: no Boost 1.92.0, so no boost-url arm")
endif()
set(MSERVER_EXTERNALS "${_externals_default}" CACHE STRING "External router arms")

add_library(mserver_external STATIC src/external.cpp "${_bench}/core/route.cpp")
target_include_directories(mserver_external PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/src/shim"
                                                   "${CMAKE_CURRENT_SOURCE_DIR}/src" "${_bench}")
target_link_libraries(mserver_external PUBLIC mserver_http1)
target_compile_options(mserver_external PRIVATE ${_warn})

set(_arm_objects "")
function(rb_arm name source)
    string(REPLACE "-" "_" _t "arm_${name}")
    add_library(${_t} OBJECT "${_bench}/${source}")
    target_link_libraries(${_t} PRIVATE mserver_external ${ARGN})
    target_compile_options(${_t} PRIVATE ${_warn})
    set(_arm_objects ${_arm_objects} ${_t} PARENT_SCOPE)
    set(_arm_libs_${_t} ${ARGN} PARENT_SCOPE)
endfunction()
foreach(_arm IN LISTS MSERVER_EXTERNALS)
    if(NOT _arm IN_LIST _externals_all)
        message(FATAL_ERROR "mserver: unknown external arm '${_arm}'")
    endif()
    include("${_bench}/cmake/arm-${_arm}.cmake")
endforeach()
if(WIN32 AND TARGET rb_crow)
    # asio's archive at the pin has asio/include as a symbolic link to ../include. Unpacked on
    # Windows it is a file link that cl cannot follow, so Crow's target takes the link's target,
    # the same headers.
    set(_crow_inc "${rb_crow_src_SOURCE_DIR}/include" "${rb_asio_src_SOURCE_DIR}/include")
    set_target_properties(rb_crow PROPERTIES INTERFACE_INCLUDE_DIRECTORIES "${_crow_inc}"
                                             INTERFACE_SYSTEM_INCLUDE_DIRECTORIES "${_crow_inc}")
endif()
message(STATUS "mserver: external arms [${MSERVER_EXTERNALS}]")

# The router arms, and the server.
add_library(mserver_arms STATIC src/arms.cpp)
target_link_libraries(mserver_arms PUBLIC mserver_http1 mserver_external)
target_compile_definitions(mserver_arms PUBLIC MSERVER_WITH_V1=$<BOOL:${MSERVER_WITH_V1}>)
target_compile_options(mserver_arms PRIVATE ${_warn})
if(MSERVER_WITH_V1)
    target_link_libraries(mserver_arms PRIVATE mserver_v1)
endif()
add_executable(mserver src/main.cpp)
target_link_libraries(mserver PRIVATE mserver_loop mserver_arms)
target_compile_options(mserver PRIVATE ${_warn})
foreach(_t IN LISTS _arm_objects)
    target_link_libraries(mserver PRIVATE ${_t} ${_arm_libs_${_t}})
endforeach()

add_executable(test_http1 tests/test_http1.cpp)
target_link_libraries(test_http1 PRIVATE mserver_http1)
target_compile_options(test_http1 PRIVATE ${_warn})
add_test(NAME http1 COMMAND test_http1)

add_executable(test_loopback tests/test_loopback.cpp)
target_link_libraries(test_loopback PRIVATE mserver_loop)
target_compile_options(test_loopback PRIVATE ${_warn})
add_test(NAME loopback COMMAND test_loopback)

if(NOT WIN32)
    # The arms' agreement on H6's tables needs t1/h6_targets, which the paper's root project builds.
    add_executable(test_agreement tests/test_agreement.cpp)
    target_link_libraries(test_agreement PRIVATE mserver_arms)
    target_compile_options(test_agreement PRIVATE ${_warn})
    foreach(_t IN LISTS _arm_objects)
        target_link_libraries(test_agreement PRIVATE ${_t} ${_arm_libs_${_t}})
    endforeach()
    if(TARGET h6_targets)
        add_test(NAME h6_agreement COMMAND "${CMAKE_COMMAND}" "-DH6_TARGETS=$<TARGET_FILE:h6_targets>"
                 "-DAGREE=$<TARGET_FILE:test_agreement>" "-DOUT=${CMAKE_CURRENT_BINARY_DIR}/h6-agreement"
                 -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/h6_agreement.cmake")
    endif()

    add_executable(test_contract tests/test_contract.cpp)
    target_compile_options(test_contract PRIVATE ${_warn})
    add_test(NAME contract COMMAND test_contract $<TARGET_FILE:mserver>)
endif()
