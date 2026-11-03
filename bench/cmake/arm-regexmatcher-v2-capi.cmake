# regexmatcher-v2-capi (design/review-runs/boundary-arms.md): RegexMatcher v2 behind its own extern "C"
# interface, in a translation unit of its own (arms/capi/v2_capi.cpp) beside the adapter's
# (arms/regexmatcher_v2_capi.cpp). Two objects of one arm target, so build.sh hashes both as the arm's
# inputs; rbench has no link-time optimisation, so the adapter reaches v2 through one call per lookup
# (tools/check_boundary_call.py checks it in the linked binary).
include(${CMAKE_CURRENT_LIST_DIR}/regexmatcher-v2.cmake)
rb_arm(regexmatcher-v2-capi arms/regexmatcher_v2_capi.cpp RegexMatcher::route)
target_sources(arm_regexmatcher_v2_capi PRIVATE arms/capi/v2_capi.cpp)
target_compile_definitions(arm_regexmatcher_v2_capi PRIVATE RB_REGEXMATCHER_COMMIT="${RB_REGEXMATCHER_COMMIT}")
