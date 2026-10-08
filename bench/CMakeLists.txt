cmake_minimum_required(VERSION 3.25)
project(rbench LANGUAGES C CXX)

# rbench: router lookups on one table and one ring per run, one arm per router
# (main.cpp). Linux x86-64 with clang; every third-party arm is fetched at a pinned
# version (cmake/pins.cmake).
#
#   -DREGEXMATCHER_DIR=<dir>    a RegexMatcher v2 checkout for the regexmatcher-v2* arms
#                               (until v2 is public, the only source of it)
#   -DRB_ARMS=a;b;...           the arms to build (default: all in RB_ALL_ARMS; an arm of
#                               RB_OPT_IN_ARMS only when named here)
#   -DRB_SANITIZER=...          address+undefined, thread or memory; applied to every
#                               target here, including the fetched arms
#   -DRB_MARCH=native           the instruction set of every C and C++ target, and with
#                               RB_RUST_TARGET_CPU and RB_GOAMD64 of the FFI arms
#                               (cmake/isa.cmake)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
    message(FATAL_ERROR "rbench builds on Linux x86-64 only (time-stamp counter, glibc malloc accounting)")
endif()

set(RB_ALL_ARMS null null-no405 radix hash std-regex regexmatcher-v1 regexmatcher-v2 regexmatcher-v2-ct regexmatcher-v2-r1
    crow oatpp boost-url r3 drogon pistache matchit httprouter nethttp gin actix-router
    uwebsockets glaze cpp-httplib chi path-tree)
set(RB_ARMS "${RB_ALL_ARMS}" CACHE STRING "Arms to build")
# Exploratory arms that no default build has: each is built only when RB_ARMS names it.
set(RB_OPT_IN_ARMS regexmatcher-v2-ct-heap)

# Sanitizers, applied here to every target, so the fetched arms are instrumented too
# (MemorySanitizer needs that).
set(RB_SANITIZER "" CACHE STRING "Sanitizer (address+undefined, thread, memory)")
if(RB_SANITIZER)
    string(REPLACE "+" "," _san "${RB_SANITIZER}")
    add_compile_options(-fsanitize=${_san} -fno-omit-frame-pointer -fno-sanitize-recover=all -g)
    add_link_options(-fsanitize=${_san})
    if(_san MATCHES "memory")
        set(RB_MSAN_LIBCXX "$ENV{HOME}/opt/libcxx-msan-gcc" CACHE PATH "MSan-instrumented libc++ prefix")
        if(NOT EXISTS "${RB_MSAN_LIBCXX}/include/c++/v1")
            message(FATAL_ERROR "RB_SANITIZER=memory needs an instrumented libc++ at RB_MSAN_LIBCXX")
        endif()
        add_compile_options(-fsanitize-memory-track-origins=2
            "$<$<COMPILE_LANGUAGE:CXX>:-stdlib=libc++>"
            "$<$<COMPILE_LANGUAGE:CXX>:-isystem${RB_MSAN_LIBCXX}/include/c++/v1>")
        add_link_options(-stdlib=libc++ "-L${RB_MSAN_LIBCXX}/lib" "-Wl,-rpath,${RB_MSAN_LIBCXX}/lib" -lc++abi)
    endif()
    message(STATUS "rbench: sanitizer ${RB_SANITIZER}")
endif()

# The instruction set: the host's own for every arm (cmake/isa.cmake), before any target or
# fetched project is defined, so every one of them inherits it.
include(cmake/isa.cmake)

include(FetchContent)
include(cmake/pins.cmake)

# nanobench: the header only.
FetchContent_Declare(nanobench URL "${RB_NANOBENCH_URL}" URL_HASH SHA256=${RB_NANOBENCH_SHA256}
                     SOURCE_SUBDIR no-cmake)
FetchContent_MakeAvailable(nanobench)
add_library(rb_nanobench INTERFACE)
target_include_directories(rb_nanobench SYSTEM INTERFACE "${nanobench_SOURCE_DIR}/src/include")

# Provenance, captured at configure time.
find_package(Git REQUIRED)
function(rb_git dir out)
    execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${dir}" rev-parse HEAD
                    OUTPUT_VARIABLE _c OUTPUT_STRIP_TRAILING_WHITESPACE RESULT_VARIABLE _rc ERROR_QUIET)
    if(NOT _rc EQUAL 0)
        set(_c "unknown")
    endif()
    set(${out} "${_c}" PARENT_SCOPE)
endfunction()
# The code commit: the last commit that changed the files compiled here, so committing
# results does not move it.
execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${CMAKE_CURRENT_SOURCE_DIR}" log -1 --format=%H --
                        main.cpp core arms cmake CMakeLists.txt coverage.json
                OUTPUT_VARIABLE RB_CODE_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
if(NOT RB_CODE_COMMIT)
    set(RB_CODE_COMMIT "unknown")
endif()

# The harness core: generators, registry, probes, driver.
add_executable(rbench main.cpp core/route.cpp core/table.cpp core/sha256.cpp core/alloc_count.cpp
               core/registry.cpp core/probe.cpp core/github_api.cpp core/cache_counters.cpp)
target_include_directories(rbench PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(rbench PRIVATE rb_nanobench)
target_compile_options(rbench PRIVATE -Wall -Wextra)

# RegexMatcher v2, for the regexmatcher-v2* arms (cmake/regexmatcher-v2.cmake sets
# RB_REGEXMATCHER_COMMIT); "none" in a build without them.
set(RB_REGEXMATCHER_COMMIT "none")
foreach(_a regexmatcher-v2 regexmatcher-v2-ct)
    if(_a IN_LIST RB_ARMS)
        include(cmake/regexmatcher-v2.cmake)
    endif()
endforeach()

target_compile_definitions(rbench PRIVATE RB_CODE_COMMIT="${RB_CODE_COMMIT}"
    RB_REGEXMATCHER_COMMIT="${RB_REGEXMATCHER_COMMIT}" RB_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
    RB_SANITIZER="${RB_SANITIZER}")
# (The instruction set is in rb_isa.h, which core/route.hpp includes; main.cpp reports it.)
message(STATUS "rbench: code ${RB_CODE_COMMIT}, RegexMatcher v2 ${RB_REGEXMATCHER_COMMIT}, arms [${RB_ARMS}]")

# One object library per arm, linked into rbench. Each arm's compiled inputs are hashed as
# their own target (arm_<name>), so a build without an arm leaves the others' hashes alone.
function(rb_arm name source)
    string(REPLACE "-" "_" _t "arm_${name}")
    add_library(${_t} OBJECT "${source}")
    target_include_directories(${_t} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    target_link_libraries(${_t} PRIVATE rb_nanobench ${ARGN})
    target_compile_options(${_t} PRIVATE -Wall -Wextra)
    target_link_libraries(rbench PRIVATE ${_t} ${ARGN})
endfunction()

# The Rust or Go sources and toolchain of an FFI arm, digested into a header the adapter
# includes, so the arm's compiled inputs (lab/bin/inputs_hash.py) change when they do.
function(rb_ffi_digest name dir header)
    set(_text "")
    foreach(_f IN LISTS ARGN)
        file(SHA256 "${dir}/${_f}" _h)
        string(APPEND _text "${_f} ${_h}; ")
    endforeach()
    string(APPEND _text "${RB_FFI_TOOLCHAIN}")
    set(_out "${CMAKE_CURRENT_BINARY_DIR}/rb-ffi/${header}")
    set(_content "// Generated: the sources and toolchain of the ${name} arm.
#define RB_FFI_SOURCES \"${_text}\"
")
    if(EXISTS "${_out}")
        file(READ "${_out}" _old)
    endif()
    if(NOT _old STREQUAL _content)
        file(WRITE "${_out}" "${_content}")
    endif()
endfunction()

foreach(_arm IN LISTS RB_ARMS)
    if(NOT _arm IN_LIST RB_ALL_ARMS AND NOT _arm IN_LIST RB_OPT_IN_ARMS)
        message(FATAL_ERROR "unknown arm '${_arm}'")
    endif()
    include(cmake/arm-${_arm}.cmake)
endforeach()
