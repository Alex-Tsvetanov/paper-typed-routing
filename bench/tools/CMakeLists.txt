# Tools built from the harness's core (bench/core) alone, with no arm and no fetched code.
#   gen_route_tests  the paper's tables as test data for RegexMatcher v2 (gen_route_tests.cpp)
#   table_digest     digests of the tables RegexMatcher v2 builds, and the build's allocations
#                    (table_digest.cpp; needs REGEXMATCHER_DIR, a RegexMatcher v2 checkout)
#   backtrack_check  rbench's model of v2's backtracking against a counting build of v2
#                    (backtrack_check.cpp; needs REGEXMATCHER_DIR with the backtracking hook and
#                    chain nodes, B1')
cmake_minimum_required(VERSION 3.25)
project(rbench_tools LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(_core "${CMAKE_CURRENT_SOURCE_DIR}/../core")
add_executable(gen_route_tests gen_route_tests.cpp "${_core}/table.cpp" "${_core}/route.cpp" "${_core}/sha256.cpp"
               "${_core}/github_api.cpp")
target_include_directories(gen_route_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/..")

set(REGEXMATCHER_DIR "" CACHE PATH "RegexMatcher v2 checkout, for table_digest")
if(REGEXMATCHER_DIR)
    add_executable(table_digest table_digest.cpp "${_core}/table.cpp" "${_core}/route.cpp" "${_core}/sha256.cpp"
                   "${_core}/github_api.cpp")
    target_include_directories(table_digest PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/.." "${REGEXMATCHER_DIR}/include")
    add_executable(backtrack_check backtrack_check.cpp "${_core}/table.cpp" "${_core}/route.cpp" "${_core}/sha256.cpp"
                   "${_core}/github_api.cpp")
    target_include_directories(backtrack_check PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/.." "${REGEXMATCHER_DIR}/include")
    set_target_properties(backtrack_check PROPERTIES EXCLUDE_FROM_ALL ON)  # built on request: it needs the hook
endif()
