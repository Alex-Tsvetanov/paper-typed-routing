#!/usr/bin/env python3
"""arms_for.py SANITIZER [--review]: the arms a sanitizer build of rbench includes, as a CMake list:
every arm in CMakeLists.txt's RB_ALL_ARMS, less those coverage.json exempts from it. With --review, the
arms of the runs after the review (RB_REVIEW_ARMS: design/review-runs/ablations.md and
boundary-arms.md) come after them, less the same exemptions: the review build and its record set.
A SANITIZER no exemption names (for example "none") gives every arm."""
import json
import re
import sys
from pathlib import Path

here = Path(__file__).parent
args = [a for a in sys.argv[1:] if a != "--review"]
if len(args) != 1:
    sys.exit(__doc__)
san = args[0]
text = (here / "CMakeLists.txt").read_text(encoding="utf-8")


def listed(name: str) -> list[str]:
    return re.search(rf"^set\({name} ([^)]*)\)", text, re.M).group(1).split()


arms = listed("RB_ALL_ARMS") + (listed("RB_REVIEW_ARMS") if "--review" in sys.argv[1:] else [])
cov = json.loads((here / "coverage.json").read_text(encoding="utf-8"))
print(";".join(a for a in arms if san not in cov.get("arm_" + a.replace("-", "_"), {}).get("not_covered_by", [])))
