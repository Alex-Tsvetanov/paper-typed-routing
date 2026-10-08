# RegexMatcher v2's tables as compile-time constants: one generated translation unit per table
# (bench/gen, written by `rbench gen-ct`), and the adapter of the run-time arm. Constant
# evaluation of a 1,000-route table takes more steps than a compiler allows by default, so the
# limit is raised for these files to 33,554,432, twice the largest need measured in round 1
# (clang 22.1.8, 16,777,216 at 1,000 routes); bench/ct_steps.py measures it again.
include(${CMAKE_CURRENT_LIST_DIR}/regexmatcher-v2.cmake)
file(GLOB _rb_ct_sources CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/gen/ct_*.cpp")
rb_arm(regexmatcher-v2-ct arms/regexmatcher_v2_ct.cpp RegexMatcher::route)
target_sources(arm_regexmatcher_v2_ct PRIVATE ${_rb_ct_sources})
target_compile_definitions(arm_regexmatcher_v2_ct PRIVATE RB_REGEXMATCHER_COMMIT="${RB_REGEXMATCHER_COMMIT}")
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    set_source_files_properties(${_rb_ct_sources} PROPERTIES COMPILE_OPTIONS "-fconstexpr-steps=33554432")
elseif(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    set_source_files_properties(${_rb_ct_sources} PROPERTIES COMPILE_OPTIONS "-fconstexpr-ops-limit=274877906944;-fconstexpr-loop-limit=8388608")
endif()
# The run-time arm defines rb::rm::find_v2, the lookup both arms call.
if(NOT "regexmatcher-v2" IN_LIST RB_ARMS)
    message(FATAL_ERROR "regexmatcher-v2-ct needs regexmatcher-v2 in RB_ARMS (it defines rb::rm::find_v2)")
endif()
