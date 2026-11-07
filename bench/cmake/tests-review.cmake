# The untimed tests of the review arms (design/review-runs/ablations.md, boundary-arms.md), run by ctest in a
# build that has any of them (bench/jobs/review-grid.sh runs them before any timing):
#   ablation_copies          tools/make_ablation.py --check: each copy is the pinned headers renamed, and each
#                            variant the copy and its one marked change
#   ablation_answers         tools/test_ablation.cpp: what each change does to the table, and every variant's
#                            answers equal the pinned code's on rbench's tables, under every method
#   ablation_objdump_copy    bench/objdump_check.sh: the copy's normalized lookup code equals the pinned
#                            headers' (IDENTICAL), at the flags the arms are compiled with (-O3, -march)
#   ablation_objdump_<v>     the same check of each variant against the copy: IDENTICAL for ab-linear,
#                            ab-hashed and ab-noexact, whose change is in the table's build only; DIFFERENT
#                            for ab-bytes, ab-heapstack and ab-strings (quick-plan.md), whose change is in the
#                            lookup
#   boundary_call            tools/check_boundary_call.py: no link-time optimisation, and the timed loop of
#                            regexmatcher-v2-capi and capi-null calls their C functions
include_guard(GLOBAL)

include(${CMAKE_CURRENT_LIST_DIR}/regexmatcher-v2.cmake)
enable_testing()
find_package(Python3 COMPONENTS Interpreter REQUIRED)

add_executable(test_ablation tools/test_ablation.cpp core/route.cpp core/table.cpp core/sha256.cpp
               core/github_api.cpp)
target_include_directories(test_ablation PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(test_ablation PRIVATE RegexMatcher::route)
target_compile_options(test_ablation PRIVATE -Wall -Wextra)
add_test(NAME ablation_answers COMMAND test_ablation)
add_test(NAME ablation_copies
         COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/make_ablation.py" --check
                 --regexmatcher "${RegexMatcher_SOURCE_DIR}")

# objdump_check.sh works in $HOME/od/<label>; the label names this build, so two builds never share it.
string(MD5 _review_od "${CMAKE_BINARY_DIR}")
string(SUBSTRING "${_review_od}" 0 10 _review_od)
set(_review_flags "")
if(RB_MARCH)
    set(_review_flags "-march=${RB_MARCH}")
endif()
set(_ab "${CMAKE_CURRENT_SOURCE_DIR}/arms/ablation")
add_test(NAME ablation_objdump_copy
         COMMAND bash "${CMAKE_CURRENT_SOURCE_DIR}/objdump_check.sh" "${CMAKE_CXX_COMPILER}"
                 "review-${_review_od}-copy" "${_ab}/route_copy.hpp" matcher::route_copy
                 "${RegexMatcher_SOURCE_DIR}/include" matcher/route.hpp matcher::route ${_review_flags})
set_tests_properties(ablation_objdump_copy PROPERTIES PASS_REGULAR_EXPRESSION "\nIDENTICAL"
                     FAIL_REGULAR_EXPRESSION "DIFFERENT")
foreach(_v ab_linear ab_hashed ab_noexact ab_bytes ab_heapstack ab_strings)
    add_test(NAME ablation_objdump_${_v}
             COMMAND bash "${CMAKE_CURRENT_SOURCE_DIR}/objdump_check.sh" "${CMAKE_CXX_COMPILER}"
                     "review-${_review_od}-${_v}" "${_ab}/route_copy.hpp" matcher::route_copy
                     "${_ab}" route_${_v}.hpp matcher::route_${_v} ${_review_flags})
    if(_v STREQUAL "ab_bytes" OR _v STREQUAL "ab_heapstack" OR _v STREQUAL "ab_strings")
        set_tests_properties(ablation_objdump_${_v} PROPERTIES PASS_REGULAR_EXPRESSION "\nDIFFERENT")
    else()
        set_tests_properties(ablation_objdump_${_v} PROPERTIES PASS_REGULAR_EXPRESSION "\nIDENTICAL"
                             FAIL_REGULAR_EXPRESSION "DIFFERENT")
    endif()
endforeach()

if("regexmatcher-v2-capi" IN_LIST RB_ARMS OR "capi-null" IN_LIST RB_ARMS)
    add_test(NAME boundary_call
             COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/check_boundary_call.py"
                     "$<TARGET_FILE:rbench>" "${CMAKE_BINARY_DIR}")
endif()
message(STATUS "rbench: the review arms' tests (cmake/tests-review.cmake)")

# The quick runs' plans and runner (quick-plan.md): the plans on disk equal quick_common.py's, and the runner's
# refusals and cuts behave as written. Nothing in it times anything.
add_test(NAME quick_unittest
         COMMAND "${Python3_EXECUTABLE}" -I -B "${CMAKE_CURRENT_SOURCE_DIR}/quick/test_quick.py")
