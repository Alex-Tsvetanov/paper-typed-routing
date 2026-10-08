# The tools of H6 (design/round2/hypotheses-v2-proposal.md), for lab/t1 on the lab host L; rbench
# has its own project in bench/. This file is at the paper's root so that bench/core, which
# h6_targets compiles, and server/ are first-party to lab/bin/inputs_hash.py (it counts files
# under the top-level source directory).
#   h6_targets  the routes of one H6 table and one request target per route (rbench's generator,
#               bench/core, compiled here unchanged; t1/h6_targets.cpp)
#   mserver     the paper's minimal HTTP/1.1 server, one binary with three router arms (v2, v1,
#               null), and its tests (server/; design/round2/minimal-server.md)
# RegexMatcher v2 comes from REGEXMATCHER_DIR until v2 is public; v1 is fetched, pinned by commit
# and sha256 (bench/cmake/pins.cmake).
cmake_minimum_required(VERSION 3.25)
project(p2_h6 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
enable_testing()

# Sanitizers, applied to every target here, as rbench does (bench/CMakeLists.txt); MemorySanitizer
# needs an instrumented libc++.
set(P2_SANITIZER "" CACHE STRING "Sanitizer (address+undefined, thread, memory)")
if(P2_SANITIZER)
    string(REPLACE "+" "," _san "${P2_SANITIZER}")
    add_compile_options(-fsanitize=${_san} -fno-omit-frame-pointer -fno-sanitize-recover=all -g)
    add_link_options(-fsanitize=${_san})
    if(_san MATCHES "memory")
        set(P2_MSAN_LIBCXX "$ENV{HOME}/opt/libcxx-msan-gcc" CACHE PATH "MSan-instrumented libc++ prefix")
        if(NOT EXISTS "${P2_MSAN_LIBCXX}/include/c++/v1")
            message(FATAL_ERROR "P2_SANITIZER=memory needs an instrumented libc++ at P2_MSAN_LIBCXX")
        endif()
        add_compile_options(-fsanitize-memory-track-origins=2
            "$<$<COMPILE_LANGUAGE:CXX>:-stdlib=libc++>"
            "$<$<COMPILE_LANGUAGE:CXX>:-isystem${P2_MSAN_LIBCXX}/include/c++/v1>")
        add_link_options(-stdlib=libc++ "-L${P2_MSAN_LIBCXX}/lib" "-Wl,-rpath,${P2_MSAN_LIBCXX}/lib" -lc++abi)
    endif()
    message(STATUS "h6: sanitizer ${P2_SANITIZER}")
endif()

# The instruction set: the host's own, as for rbench's arms (bench/cmake/isa.cmake: -march=native
# on every C and C++ target, the fetched v1 included), before any target is defined.
include("${CMAKE_CURRENT_SOURCE_DIR}/bench/cmake/isa.cmake")

set(_bench "${CMAKE_CURRENT_SOURCE_DIR}/bench")
add_executable(h6_targets t1/h6_targets.cpp "${_bench}/core/table.cpp" "${_bench}/core/route.cpp"
    "${_bench}/core/sha256.cpp" "${_bench}/core/github_api.cpp")
target_include_directories(h6_targets PRIVATE "${_bench}")

add_subdirectory(server)
