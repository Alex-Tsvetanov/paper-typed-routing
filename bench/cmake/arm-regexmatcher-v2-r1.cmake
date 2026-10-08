# The exploratory ablation arm: the round-1 header renamed (arms/ablation/route_r1.hpp, in this
# repository), through the adapter of the v2 arms. clang before 19 needs -fsized-deallocation
# for this header (its allocator calls the sized aligned delete); RegexMatcher v2 no longer does.
rb_arm(regexmatcher-v2-r1 arms/regexmatcher_v2_r1.cpp)
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    target_compile_options(arm_regexmatcher_v2_r1 PRIVATE -fsized-deallocation)
endif()
