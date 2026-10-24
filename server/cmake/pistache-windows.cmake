# Pistache on Windows (Alex, 2026-10-23: its meson build with libevent; 2026-10-24: without its logging
# installer). In place of round 2's bench/cmake/arm-pistache.cmake, whose CMake build of Pistache has no
# Windows path, this file builds at configure time, with this project's compiler (clang-cl), Release,
# the instruction set of bench/cmake/isa.cmake and, under P2_SANITIZER=address, AddressSanitizer:
#   1. libevent 2.1.13-stable from P2_LIBEVENT_SRC with its CMake: static, no TLS, no tests, samples or
#      benchmarks, installed into the build tree;
#   2. Pistache v0.4.26 at round 2's pin (bench/cmake/pins.cmake, fetched and checked by sha256) with
#      meson (P2_MESON, meson.py of meson 1.12.1, run with this Python): its static library only, with
#      RapidJSON from the two files of its wrap (P2_RAPIDJSON_WRAP, in meson's package cache, so meson
#      downloads nothing). Pistache's src/meson.build would run src/winlog/installman.ps1 during the
#      build, which copies a DLL into Program Files, installs an event-log manifest and writes registry
#      keys; the one line that makes the library depend on it is removed from the fetched copy, so
#      nothing is installed. Pistache's C++ code is not changed; its log events go to a provider with
#      no installed manifest and are dropped. Its resource DLL pistachelog.dll is not built.
# meson runs in the configure's environment (the Visual Studio one, for mc.exe, with clang-cl and
# lld-link on PATH: t3/labsteps.py) and gets this build's ninja through NINJA.
# Then rb_arm(pistache arms/pistache.cpp pistache_static) adds round 2's adapter, as on Linux.
include_guard(GLOBAL)

set(P2_LIBEVENT_SRC "" CACHE PATH "libevent 2.1.13-stable's source tree (Windows)")
set(P2_MESON "" CACHE FILEPATH "meson.py of meson 1.12.1 (Windows)")
set(P2_RAPIDJSON_WRAP "" CACHE PATH "the folder with rapidjson-1.1.0.tar.gz and rapidjson_1.1.0-2_patch.zip (Windows)")
foreach(_p IN ITEMS "${P2_LIBEVENT_SRC}/CMakeLists.txt" "${P2_MESON}" "${P2_RAPIDJSON_WRAP}/rapidjson-1.1.0.tar.gz"
                    "${P2_RAPIDJSON_WRAP}/rapidjson_1.1.0-2_patch.zip")
    if(NOT EXISTS "${_p}")
        message(FATAL_ERROR "pistache on Windows: no ${_p} (set P2_LIBEVENT_SRC, P2_MESON, P2_RAPIDJSON_WRAP)")
    endif()
endforeach()
find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(_p2_flags "/clang:-march=${RB_MARCH}")
set(_p2_meson_san "")
if(P2_SANITIZER STREQUAL "address")
    string(APPEND _p2_flags " /fsanitize=address")
    set(_p2_meson_san "-Db_sanitize=address")
endif()
set(_p2_dir "${CMAKE_BINARY_DIR}/_p2")

function(_p2_run what)
    execute_process(COMMAND ${ARGN} RESULT_VARIABLE _rc OUTPUT_VARIABLE _out ERROR_VARIABLE _out)
    file(WRITE "${_p2_dir}/${what}.log" "${_out}")
    if(NOT _rc EQUAL 0)
        message(FATAL_ERROR "pistache on Windows: ${what} failed (${_rc}); see ${_p2_dir}/${what}.log")
    endif()
endfunction()

# 1. libevent.
set(_p2_libevent "${_p2_dir}/libevent")
if(NOT EXISTS "${_p2_libevent}/lib/cmake/libevent/LibeventConfig.cmake")
    _p2_run(libevent-configure "${CMAKE_COMMAND}" -S "${P2_LIBEVENT_SRC}" -B "${_p2_dir}/libevent-build" -G Ninja
            "-DCMAKE_MAKE_PROGRAM=${CMAKE_MAKE_PROGRAM}" "-DCMAKE_C_COMPILER=${CMAKE_C_COMPILER}"
            -DCMAKE_BUILD_TYPE=Release "-DCMAKE_C_FLAGS=${_p2_flags}" -DCMAKE_POLICY_VERSION_MINIMUM=3.5
            -DEVENT__LIBRARY_TYPE=STATIC -DEVENT__DISABLE_OPENSSL=ON -DEVENT__DISABLE_MBEDTLS=ON
            -DEVENT__DISABLE_TESTS=ON -DEVENT__DISABLE_SAMPLES=ON -DEVENT__DISABLE_BENCHMARK=ON
            -DEVENT__DISABLE_REGRESS=ON "-DCMAKE_INSTALL_PREFIX=${_p2_libevent}")
    _p2_run(libevent-build "${CMAKE_COMMAND}" --build "${_p2_dir}/libevent-build" --target install)
endif()
find_package(Libevent 2.1.13 EXACT REQUIRED CONFIG PATHS "${_p2_libevent}/lib/cmake/libevent" NO_DEFAULT_PATH)

# 2. Pistache: the pinned source, without its logging installer, and meson's package cache.
FetchContent_Declare(rb_pistache_src URL "https://codeload.github.com/pistacheio/pistache/tar.gz/${RB_PISTACHE_COMMIT}"
                     URL_HASH SHA256=${RB_PISTACHE_SHA256} SOURCE_SUBDIR no-cmake)
FetchContent_MakeAvailable(rb_pistache_src)
set(_p2_src "${rb_pistache_src_SOURCE_DIR}")
file(READ "${_p2_src}/src/meson.build" _p2_mb)
set(_p2_old "    deps_libpistache += gen_logging_txtfl_dep\n")
set(_p2_new "    # p2r3: the logging manifest is not installed at build time (server/cmake/pistache-windows.cmake)\n")
string(FIND "${_p2_mb}" "${_p2_new}" _p2_done)
if(_p2_done EQUAL -1)
    string(REPLACE "${_p2_old}" "" _p2_rest "${_p2_mb}")
    string(LENGTH "${_p2_mb}" _l0)
    string(LENGTH "${_p2_rest}" _l1)
    string(LENGTH "${_p2_old}" _l2)
    math(EXPR _p2_count "(${_l0} - ${_l1}) / ${_l2}")
    if(NOT _p2_count EQUAL 1)
        message(FATAL_ERROR "pistache on Windows: src/meson.build has the installer line ${_p2_count} times, not once")
    endif()
    string(REPLACE "${_p2_old}" "${_p2_new}" _p2_mb "${_p2_mb}")
    file(WRITE "${_p2_src}/src/meson.build" "${_p2_mb}")
endif()
file(COPY "${P2_RAPIDJSON_WRAP}/rapidjson-1.1.0.tar.gz" "${P2_RAPIDJSON_WRAP}/rapidjson_1.1.0-2_patch.zip"
     DESTINATION "${_p2_src}/subprojects/packagecache")

set(_p2_build "${_p2_dir}/pistache-build")
set(_p2_lib "${_p2_build}/src/libpistache.a")
if(NOT EXISTS "${_p2_lib}")
    set(_p2_env "${CMAKE_COMMAND}" -E env "CC=${CMAKE_C_COMPILER}" "CXX=${CMAKE_CXX_COMPILER}"
                "NINJA=${CMAKE_MAKE_PROGRAM}")
    _p2_run(pistache-setup ${_p2_env} "${Python3_EXECUTABLE}" "${P2_MESON}" setup "${_p2_build}" "${_p2_src}"
            --buildtype=release -Db_ndebug=true --default-library=static --wrap-mode=nodownload ${_p2_meson_san}
            -DPISTACHE_USE_SSL=false -DPISTACHE_BUILD_TESTS=false -DPISTACHE_BUILD_EXAMPLES=false
            -DPISTACHE_BUILD_DOCS=false -DPISTACHE_INSTALL=false "-Dcpp_args=/clang:-march=${RB_MARCH}"
            "--cmake-prefix-path=${_p2_libevent}")
    _p2_run(pistache-compile ${_p2_env} "${Python3_EXECUTABLE}" "${P2_MESON}" compile -C "${_p2_build}"
            pistache:static_library)
endif()

add_library(pistache_static STATIC IMPORTED GLOBAL)
set(_p2_inc "${_p2_build}/include" "${_p2_src}/include" "${_p2_src}/subprojects/hinnant-date/include"
            "${_p2_src}/subprojects/rapidjson-1.1.0/include")
set_target_properties(pistache_static PROPERTIES IMPORTED_LOCATION "${_p2_lib}"
                                                 INTERFACE_INCLUDE_DIRECTORIES "${_p2_inc}"
                                                 INTERFACE_SYSTEM_INCLUDE_DIRECTORIES "${_p2_inc}")
target_link_libraries(pistache_static INTERFACE libevent::core libevent::extra ws2_32 dbghelp iphlpapi mswsock)
rb_arm(pistache arms/pistache.cpp pistache_static)
message(STATUS "pistache on Windows: ${_p2_lib} (meson, libevent ${Libevent_VERSION})")
