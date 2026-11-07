# An ablation arm of quick-plan.md (beside those of design/review-runs/ablations.md): RegexMatcher v2's route
# headers renamed (arms/ablation/route_ab_strings.hpp, tools/make_ablation.py) with one change: a captured value
# owns a std::string copy of its bytes. Its adapter keeps the last Match (arms/regexmatcher_v2_ab_strings.cpp).
rb_arm(regexmatcher-v2-ab-strings arms/regexmatcher_v2_ab_strings.cpp)
