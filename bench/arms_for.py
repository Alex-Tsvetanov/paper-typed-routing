#!/usr/bin/env python3
"""arms_for.py SANITIZER: the arms a sanitizer build of rbench includes, as a CMake list:
every arm in CMakeLists.txt's RB_ALL_ARMS, less those coverage.json exempts from it."""
import json
import re
import sys
from pathlib import Path

here = Path(__file__).parent
san = sys.argv[1]
arms = re.search(r"^set\(RB_ALL_ARMS ([^)]*)\)", (here / "CMakeLists.txt").read_text(encoding="utf-8"), re.M).group(1).split()
cov = json.loads((here / "coverage.json").read_text(encoding="utf-8"))
print(";".join(a for a in arms if san not in cov.get("arm_" + a.replace("-", "_"), {}).get("not_covered_by", [])))
