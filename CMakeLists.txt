# The tools of H6 (design/round2/hypotheses-v2-proposal.md), for lab/t1 on the lab host L; rbench
# has its own project in bench/. This file is at the paper's root so that bench/core, which
# h6_targets compiles, and server/ are first-party to lab/bin/inputs_hash.py (it counts files
# under the top-level source directory).
#   h6_targets  the routes of one H6 table and one request target per route (rbench's generator,
#               bench/core, compiled here unchanged; t1/h6_targets.cpp)
#   e2e_requests  round 3's request sets (t3/; design/round3/end-to-end.md, section 4)
#   mserver     the paper's minimal HTTP/1.1 server, one binary with the router chosen at start:
#               v2, v1 (Linux), null and round 2's C and C++ adapters, and its tests (server/;
#               design/round2/minimal-server.md, design/round3/end-to-end.md)
# RegexMatcher v2 is fetched at release 2.1.0.0, v1 at d16f30a8, each pinned by commit and sha256
# (bench/cmake/pins.cmake); a checkout given as REGEXMATCHER_DIR takes precedence for v2.
cmake_minimum_required(VERSION 3.25)
project(p2_h6 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
enable_testing()

# Sanitizers, applied to every target here, as rbench does (bench/CMakeLists.txt); MemorySanitizer
# needs an instrumented libc++.
set(P2_SANITIZER "" CACHE STRING "Sanitizer (address+undefined, thread, memory; with MSVC: address)")
if(P2_SANITIZER AND MSVC)
    # MSVC's AddressSanitizer, the Windows records' sanitizer (CLAUDE.md, D5).
    if(NOT P2_SANITIZER STREQUAL "address")
        message(FATAL_ERROR "with MSVC, P2_SANITIZER can only be address")
    endif()
    add_compile_options(/fsanitize=address /Zi)
    add_link_options(/INCREMENTAL:NO /DEBUG)
    message(STATUS "h6: sanitizer ${P2_SANITIZER} (MSVC)")
elseif(P2_SANITIZER)
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

# Round 3's request sets (design/round3/end-to-end.md, section 4): the same generator, with the T0
# ring and the expected answers.
add_executable(e2e_requests t3/e2e_requests.cpp "${_bench}/core/table.cpp" "${_bench}/core/route.cpp"
    "${_bench}/core/sha256.cpp" "${_bench}/core/github_api.cpp")
target_include_directories(e2e_requests PRIVATE "${_bench}")

add_subdirectory(server)
