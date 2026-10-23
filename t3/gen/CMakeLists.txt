# p2gen, the HTTP/1.1 load generator of P2's end-to-end block (design/round3/end-to-end.md, section
# 8), and p2gen_tests, the unit tests of its pure code. Built from the paper's root CMakeLists.txt
# (add_subdirectory(t3/gen)). Standard library and the system's sockets only: epoll on Linux, an
# I/O completion port on Windows.
#
#   -DP2GEN_COMMIT=<hash>   the commit text the JSON line carries (default: unknown)
cmake_minimum_required(VERSION 3.25)

if(MSVC)
    # As the server's: the standard's preprocessor and __cplusplus, UTF-8 sources, conforming mode.
    add_compile_options(/Zc:__cplusplus /Zc:preprocessor /utf-8 /permissive- /EHsc)
    add_compile_definitions(_WIN32_WINNT=0x0A00 WIN32_LEAN_AND_MEAN NOMINMAX)
    set(_warn /W3)
else()
    set(_warn -Wall -Wextra)
endif()

find_package(Threads REQUIRED)

# The code with no I/O: options, requests, the answer parser, the histogram and the report.
add_library(p2gen_core STATIC framing.cpp options.cpp report.cpp requests.cpp)
target_include_directories(p2gen_core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_options(p2gen_core PRIVATE ${_warn})

if(WIN32)
    set(_net net_iocp.cpp)
else()
    set(_net net_epoll.cpp)
endif()
add_executable(p2gen p2gen.cpp worker.cpp ${_net})
target_link_libraries(p2gen PRIVATE p2gen_core Threads::Threads)
if(WIN32)
    target_link_libraries(p2gen PRIVATE ws2_32)
endif()
target_compile_options(p2gen PRIVATE ${_warn})
set(P2GEN_COMMIT "unknown" CACHE STRING "The commit text of p2gen's JSON line")
target_compile_definitions(p2gen PRIVATE "P2GEN_COMMIT=\"${P2GEN_COMMIT}\"")

add_executable(p2gen_tests p2gen_tests.cpp)
target_link_libraries(p2gen_tests PRIVATE p2gen_core)
target_compile_options(p2gen_tests PRIVATE ${_warn})
add_test(NAME p2gen_tests COMMAND p2gen_tests)

# Functional tests of count mode (count_checks.py): a scripted server for the framing, timeout and
# reconnect cases. Untimed: they measure nothing.
find_package(Python3 COMPONENTS Interpreter QUIET)
if(Python3_Interpreter_FOUND)
    add_test(NAME p2gen_edge COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/count_checks.py" edge
             --p2gen $<TARGET_FILE:p2gen>)
endif()
