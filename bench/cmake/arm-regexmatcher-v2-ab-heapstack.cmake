# An ablation arm of quick-plan.md (beside those of design/review-runs/ablations.md): RegexMatcher v2's route headers renamed
# (arms/ablation/route_ab_heapstack.hpp, tools/make_ablation.py) with one change: the walk's choice stack in a heap block, one allocation per walk.
rb_arm(regexmatcher-v2-ab-heapstack arms/regexmatcher_v2_ab_heapstack.cpp)
