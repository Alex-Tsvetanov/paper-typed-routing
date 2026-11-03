#!/usr/bin/env python3
"""Tests of t3/round1_macros.py: the committed file is what round 1's tables give, the frozen bounds are the frozen
text's (when its commit is in the clone), a row whose holds column the bounds do not give is refused, and no value
holds a dash.

    python t3/test_round1_macros.py          (or: python -m pytest t3/test_round1_macros.py)
"""
from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import round1_macros as R  # noqa: E402

RESULTS = ROOT / "results"
OUT = RESULTS / "round3" / "round1-macros.tex"
INPUTS = ("tab_h1.csv", "sens_h1.csv", "tab_h2.csv", "sens_h4.csv", "tab_h7.csv", "sens_h7.csv", "tab_h6.csv")


def frozen_text() -> str | None:
    p = subprocess.run(["git", "-C", str(ROOT), "show", f"{R.FROZEN_COMMIT}:hypotheses.md"], capture_output=True,
                       text=True, encoding="utf-8")
    return " ".join(p.stdout.split()) if p.returncode == 0 else None


class Round1MacroTests(unittest.TestCase):
    def test_the_committed_file_is_current(self) -> None:
        self.assertEqual(OUT.read_text(encoding="utf-8"), R.generate(RESULTS))

    def test_the_frozen_bounds_are_the_frozen_texts(self) -> None:
        text = frozen_text()
        if text is None:
            self.skipTest(f"{R.FROZEN_COMMIT} is not in this clone")
        self.assertIn(f"interval inside [{R.BAND[0]:.2f}, {R.BAND[1]:.2f}]", text)
        self.assertIn(f"the lower bound of that interval is above {R.BOUND:g}", text)
        self.assertIn(f"at m = {R.SMALL}, in each of the seven shapes", text)
        self.assertIn(f"at m = {R.LARGE:,} in the rest and param-last shapes", text)

    def test_a_holds_column_the_bounds_do_not_give_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name in INPUTS:
                shutil.copy(RESULTS / name, tmp / name)
            rows = list(csv.DictReader((tmp / "tab_h6.csv").open(encoding="utf-8")))
            rows[0]["holds"] = "True" if rows[0]["holds"] == "False" else "False"
            with (tmp / "tab_h6.csv").open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
            with self.assertRaisesRegex(ValueError, "the frozen bounds give"):
                R.generate(tmp)

    def test_the_counts_agree_with_each_other(self) -> None:
        m = dict(re.findall(r"\\newcommand\{\\(\w+)\}\{([^}]*)\}", OUT.read_text(encoding="utf-8")))
        self.assertEqual(int(m["RoundOneHSixSmallCells"]) + int(m["RoundOneHSixLargeCells"]),
                         len(list(csv.DictReader((RESULTS / "tab_h6.csv").open(encoding="utf-8")))))
        self.assertLessEqual(int(m["RoundOneHSixComparable"]),
                             int(m["RoundOneHSixSmallCells"]) + int(m["RoundOneHSixLargeCells"]))
        self.assertLessEqual(float(m["RoundOneHSixDiffRatioLow"]), float(m["RoundOneHSixDiffRatioHigh"]))

    def test_no_dash(self) -> None:
        self.assertNotRegex(OUT.read_text(encoding="utf-8"), "[\u2013\u2014]|--")


if __name__ == "__main__":
    unittest.main(verbosity=1)
