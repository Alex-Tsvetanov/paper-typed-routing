# The adversarial tool (tools/adversarial.cpp, design/review-runs/adversarial.md), built with the
# regexmatcher-v2 arm: RegexMatcher v2 at the pinned commit through the arm's adapter and the
# harness's timing loop (core/runner.hpp), and the counting copy (tools/route_count.hpp), in one
# target of rbench's build, so build.sh hashes what it compiled and rbench's sanitizer records cover
# it. Nothing in core or in the arms changes for it. Tests (ctest): test_adversarial, the self-test,
# and the copy against the pinned headers (tools/make_route_count.py --check).
include_guard(GLOBAL)

set(_adv_sources tools/adversarial_cells.cpp tools/adversarial_pinned.cpp tools/adversarial_count.cpp
    core/route.cpp core/table.cpp core/sha256.cpp core/github_api.cpp)
# The commit of the files the tool is built from (the last commit that touched any of them): the
# code_commit of every result line. This is the one path set for it. The timed job
# (jobs/adversarial.sh) takes its code_commit from the file written below, not from a list of its
# own, so a run carries one code_commit.
set(_adv_code_paths
    tools/adversarial.hpp tools/adversarial.cpp tools/adversarial_cells.cpp tools/adversarial_pinned.cpp
    tools/adversarial_count.cpp tools/test_adversarial.cpp tools/route_count.hpp
    core arms/rm_arm.hpp arms/rm_v2.hpp cmake CMakeLists.txt)
execute_process(COMMAND "${GIT_EXECUTABLE}" -C "${CMAKE_CURRENT_SOURCE_DIR}" log -1 --format=%H -- ${_adv_code_paths}
                OUTPUT_VARIABLE ADV_CODE_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
if(NOT ADV_CODE_COMMIT)
    set(ADV_CODE_COMMIT "unknown")
endif()
file(WRITE "${CMAKE_BINARY_DIR}/adversarial-code-commit.txt" "${ADV_CODE_COMMIT}\n")

# core/registry.cpp holds nanobench's implementation.
add_executable(adversarial tools/adversarial.cpp ${_adv_sources} core/alloc_count.cpp core/cache_counters.cpp
               core/registry.cpp)
target_include_directories(adversarial PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(adversarial PRIVATE rb_nanobench RegexMatcher::route)
target_compile_options(adversarial PRIVATE -Wall -Wextra)
target_compile_definitions(adversarial PRIVATE ADV_CODE_COMMIT="${ADV_CODE_COMMIT}"
    RB_REGEXMATCHER_COMMIT="${RB_REGEXMATCHER_COMMIT}" RB_BUILD_TYPE="${CMAKE_BUILD_TYPE}"
    RB_SANITIZER="${RB_SANITIZER}")

add_executable(test_adversarial tools/test_adversarial.cpp ${_adv_sources})
target_include_directories(test_adversarial PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(test_adversarial PRIVATE RegexMatcher::route)
target_compile_options(test_adversarial PRIVATE -Wall -Wextra)

enable_testing()
add_test(NAME adversarial_unit COMMAND test_adversarial)
add_test(NAME adversarial_self_test COMMAND adversarial self-test)
# The copy's check needs Python: without it the test would silently be missing from a build that
# is gated on its tests, so a build without Python stops here.
find_package(Python3 COMPONENTS Interpreter)
if(NOT Python3_Interpreter_FOUND)
    message(FATAL_ERROR "the adversarial tool needs Python 3 for its adversarial_copy test (the counting copy "
                        "against the pinned headers)")
endif()
add_test(NAME adversarial_copy
         COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/make_route_count.py" --check
                 --regexmatcher "${RegexMatcher_SOURCE_DIR}")
message(STATUS "rbench: adversarial tool, code ${ADV_CODE_COMMIT}")
