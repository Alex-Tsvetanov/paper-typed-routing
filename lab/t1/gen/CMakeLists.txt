# t1gen (load generator) and t1null (null responder) for the T1 tier.
# Linux only. Presets asan, tsan and msan are the sanitizer record for this directory
# (lab/bin/sanitize.sh with SRC_SUBDIR=lab/t1/gen); the measured build is plain Release.
cmake_minimum_required(VERSION 3.20)
project(t1gen C)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(T1GEN_COMMIT "unknown" CACHE STRING "Papers commit the generator is built from")
set(T1_SANITIZER "" CACHE STRING "address+undefined, thread, memory or empty")

if(T1_SANITIZER STREQUAL "address+undefined")
    set(_san -fsanitize=address,undefined -fno-sanitize-recover=all)
elseif(T1_SANITIZER STREQUAL "thread")
    set(_san -fsanitize=thread)
elseif(T1_SANITIZER STREQUAL "memory")
    set(_san -fsanitize=memory -fsanitize-memory-track-origins=2)
elseif(NOT T1_SANITIZER STREQUAL "")
    message(FATAL_ERROR "unknown T1_SANITIZER '${T1_SANITIZER}'")
endif()
if(_san)
    add_compile_options(${_san} -fno-omit-frame-pointer -g)
    add_link_options(${_san})
endif()

find_package(Threads REQUIRED)
foreach(_t t1gen t1null)
    add_executable(${_t} ${_t}.c)
    target_compile_options(${_t} PRIVATE -Wall -Wextra -Werror)
    target_link_libraries(${_t} PRIVATE Threads::Threads)
endforeach()
target_compile_definitions(t1gen PRIVATE T1GEN_COMMIT="${T1GEN_COMMIT}")

enable_testing()
foreach(_case closed-depth1 closed-depth16 open-loop dropped-pipeline paths-depth1 paths-depth16 paths-invalid)
    add_test(NAME ${_case}
             COMMAND sh ${CMAKE_CURRENT_SOURCE_DIR}/selftest.sh ${_case}
                     $<TARGET_FILE:t1gen> $<TARGET_FILE:t1null>)
endforeach()
