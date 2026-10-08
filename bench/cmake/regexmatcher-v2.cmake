# RegexMatcher v2, the route matcher the paper measures, for the regexmatcher-v2 and
# regexmatcher-v2-ct arms: from a checkout (REGEXMATCHER_DIR) until v2 is public, then from its
# pinned release archive (cmake/pins.cmake). Only the library's targets are added: its tests and
# benchmarks stay off when it is not the top-level project. Its root calls
# project(RegexMatcher), which puts RegexMatcher_SOURCE_DIR in the cache, where the inputs gate
# finds it (build.sh: inputs_hash.py --dep-root regexmatcher=RegexMatcher_SOURCE_DIR).
include_guard(GLOBAL)

set(REGEXMATCHER_DIR "" CACHE PATH "RegexMatcher v2 source checkout (until v2 is public)")
if(REGEXMATCHER_DIR)
    get_filename_component(_rm "${REGEXMATCHER_DIR}" ABSOLUTE)
    if(NOT EXISTS "${_rm}/include/matcher/route.hpp")
        message(FATAL_ERROR "REGEXMATCHER_DIR=${_rm} has no include/matcher/route.hpp")
    endif()
    add_subdirectory("${_rm}" regexmatcher EXCLUDE_FROM_ALL)
    rb_git("${_rm}" RB_REGEXMATCHER_COMMIT)
    # A snapshot (git archive) is not a checkout: its commit is given instead.
    set(REGEXMATCHER_COMMIT "" CACHE STRING "the commit of REGEXMATCHER_DIR when it is not a git checkout")
    if(RB_REGEXMATCHER_COMMIT STREQUAL "unknown" AND REGEXMATCHER_COMMIT)
        set(RB_REGEXMATCHER_COMMIT "${REGEXMATCHER_COMMIT}")
    endif()
elseif(RB_REGEXMATCHER_V2_COMMIT)
    FetchContent_Declare(regexmatcher
        URL "https://codeload.github.com/cpp-for-everything/RegexMatcher/tar.gz/${RB_REGEXMATCHER_V2_COMMIT}"
        URL_HASH SHA256=${RB_REGEXMATCHER_V2_SHA256})
    FetchContent_MakeAvailable(regexmatcher)
    set(RB_REGEXMATCHER_COMMIT "${RB_REGEXMATCHER_V2_COMMIT}")
else()
    message(FATAL_ERROR "the regexmatcher-v2 arms need REGEXMATCHER_DIR (v2 has no public release to pin yet)")
endif()
if(NOT TARGET RegexMatcher::route)
    message(FATAL_ERROR "RegexMatcher at ${REGEXMATCHER_DIR} has no RegexMatcher::route target (not v2)")
endif()
