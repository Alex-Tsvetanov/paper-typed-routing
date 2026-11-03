# capi-null (design/review-runs/boundary-arms.md): an empty function behind the C shape of
# regexmatcher-v2-capi, in a translation unit of its own (arms/capi/null_capi.cpp) beside the adapter's.
rb_arm(capi-null arms/capi_null.cpp)
target_sources(arm_capi_null PRIVATE arms/capi/null_capi.cpp)
