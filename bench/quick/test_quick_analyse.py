"""Tests of the quick analysis's pure parts (bench/quick/quick_analyse.py). Nothing here reads an archive.

    python -B bench/quick/test_quick_analyse.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import quick_analyse as qa  # noqa: E402
from macros_util import Macros  # noqa: E402


class Series(unittest.TestCase):
    def test_ratio_per_round_median_min_max(self):
        s = qa.series({0: 2.0, 1: 3.0, 2: 4.0}, {0: 1.0, 1: 1.0, 2: 2.0})
        self.assertEqual((s["n"], s["median"], s["min"], s["max"]), (3, 2.0, 2.0, 3.0))
        self.assertEqual(s["left_out"], [])

    def test_a_round_missing_on_one_side_is_listed_not_used(self):
        s = qa.series({0: 2.0, 1: 3.0}, {0: 1.0})
        self.assertEqual(s["n"], 1)
        self.assertEqual(s["left_out"], ["1"])

    def test_no_common_round_gives_no_value(self):
        self.assertEqual(qa.series({0: 1.0}, {1: 1.0})["n"], 0)


class Macro(unittest.TestCase):
    def test_summary_over_cells_counts_sides_of_one(self):
        mc = Macros()
        cells = [{"n": 3, "median": m, "min": m - 0.05, "max": m + 0.05} for m in (0.9, 1.0, 1.2, 1.5)]
        cells += [None, {"n": 0}]
        qa.summary_over_cells(mc, "QuickX", cells)
        got = {n: v for n, v, _ in mc.items}
        self.assertEqual(got["QuickXCells"], "4")
        self.assertEqual(got["QuickXCellsMaxAtLeastOne"], "3")
        self.assertEqual(got["QuickXCellsMinAtMostOne"], "2")
        self.assertEqual(got["QuickXCellsAboveOne"], "2")
        self.assertEqual(got["QuickXCellsBelowOne"], "1")
        self.assertEqual(got["QuickXCellMedianMin"], "0.9000")
        self.assertEqual(got["QuickXCellMedianMax"], "1.5000")


class Objdump(unittest.TestCase):
    def test_the_ctest_line_parses(self):
        line = ("review-f3995ef2e7-ab_strings (clang version 22.1.8; flags -O3 -DNDEBUG -std=c++23 -march=native): "
                "functions 4 and 7, lines 1107 and 1766, sha256 385787fbb596ef3d and 6b5652374ed81e21")
        m = qa.OBJDUMP.match(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "ab_strings")
        self.assertEqual((m.group(5), m.group(7)), ("7", "1766"))


if __name__ == "__main__":
    unittest.main()
