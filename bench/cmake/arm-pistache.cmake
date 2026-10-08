set(PISTACHE_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(PISTACHE_USE_SSL OFF CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(CMAKE_POLICY_VERSION_MINIMUM 3.5)  # RapidJSON v1.1.0 declares cmake_minimum_required(2.8)
FetchContent_Declare(rb_pistache_src URL "https://codeload.github.com/pistacheio/pistache/tar.gz/${RB_PISTACHE_COMMIT}"
                     URL_HASH SHA256=${RB_PISTACHE_SHA256})
FetchContent_MakeAvailable(rb_pistache_src)
unset(CMAKE_POLICY_VERSION_MINIMUM)
rb_arm(pistache arms/pistache.cpp pistache_static)
# Pistache v0.4.26's include/pistache/async.h uses std::exception_ptr and std::terminate
# without including <exception>. libstdc++ supplies it through other headers; the
# instrumented libc++ of the MemorySanitizer build does not. That build alone gets the
# header by -include; no first-party file changes.
if(RB_SANITIZER MATCHES "memory")
    target_compile_options(pistache PRIVATE -include exception)
    target_compile_options(arm_pistache PRIVATE -include exception)
endif()
