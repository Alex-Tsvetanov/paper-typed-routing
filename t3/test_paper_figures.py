#!/usr/bin/env python3
"""Tests of t3/paper_figures.py: every plotted value equals the macro the text prints for it, the committed figures are
what the committed inputs give, a bad interval is refused, a missing value is left out and named, and no output
holds a dash.

    python t3/test_figures.py          (or: python -m pytest t3/test_figures.py)
"""
from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "analysis"))

import paper_figures as F  # noqa: E402
from macros_util import SHAPE_WORD, SIZE_WORD  # noqa: E402
from test_rr_macros import macros_of  # noqa: E402

SUMMARY = ROOT / "results" / "round2" / "summary.json"
DESIGN = ROOT / "design" / "round3"
PLAN = HERE / "plans" / "rr-W.json"
OUT = ROOT / "results" / "round3" / "figures"


def load_systems() -> dict:
    return {system: json.loads((DESIGN / f"floor-{letter}.json").read_text(encoding="utf-8"))
            ["analysis"]["systems"][system] for system, _, letter in F.SYSTEMS}


class LookupFigure(unittest.TestCase):
    def setUp(self):
        self.summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        self.macros = macros_of((ROOT / "results" / "round2" / "macros.tex").read_text(encoding="utf-8"))

    def test_every_value_is_its_macro(self):
        rows = F.lookup_rows(self.summary)
        seen = 0
        for shape, cells in rows.items():
            for m, r, lo, hi in cells:
                w = SHAPE_WORD[shape] + SIZE_WORD[m]
                self.assertEqual((r, lo, hi), (self.macros[f"HOneRatio{w}"], self.macros[f"HOneLow{w}"],
                                               self.macros[f"HOneHigh{w}"]), w)
                seen += 1
        self.assertEqual(seen, sum(1 for k in self.macros if k.startswith("HOneRatio")))
        paper = macros_of((ROOT / "results" / "round3" / "round2-paper-macros.tex").read_text(encoding="utf-8"))
        self.assertEqual(Decimal(F.ratio(self.summary["h1"]["margin"])), Decimal(paper["Margin"]))

    def test_the_file_plots_each_cell_with_its_interval(self):
        text = F.lookup_figure(self.summary)
        for cells in F.lookup_rows(self.summary).values():
            for m, r, lo, hi in cells:
                self.assertIn(f"({m},{r}) += (0,{Decimal(hi) - Decimal(r)}) -= (0,{Decimal(r) - Decimal(lo)})", text)
        self.assertEqual(text.count("\\nextgroupplot"), len(F.SHAPES))

    def test_an_interval_that_misses_its_ratio_is_refused(self):
        bad = copy.deepcopy(self.summary)
        cell = next(c for c in bad["h1_cells"] if c.get("status") == "tested")
        cell["ci_low"] = cell["ratio"] + 0.01
        with self.assertRaises(ValueError):
            F.lookup_figure(bad)

    def test_a_bound_above_the_top_is_refused(self):
        bad = copy.deepcopy(self.summary)
        cell = next(c for c in bad["h1_cells"] if c.get("status") == "tested")
        cell["ci_high"] = float(F.RATIO_YMAX)
        with self.assertRaises(ValueError):
            F.lookup_figure(bad)


class EndToEndFigure(unittest.TestCase):
    def setUp(self):
        self.systems = load_systems()
        self.sizes = json.loads(PLAN.read_text(encoding="utf-8"))["sizes"]
        self.macros = macros_of((ROOT / "results" / "round3" / "macros.tex").read_text(encoding="utf-8"))

    def test_every_value_is_its_macro(self):
        rows = F.e2e_rows(self.systems, self.sizes)
        words = {system: word for system, word, _ in F.SYSTEMS}
        self.assertEqual(len(rows), len(F.SYSTEMS) * len(self.sizes))
        for (system, m), programs in rows.items():
            for pword, *vals in programs:
                name = f"RThree{words[system]}{pword}{SIZE_WORD[m]}"
                for field, v in zip(("Lead", "Floor", "KSpan"), vals):
                    want = self.macros[name + field]
                    self.assertEqual(v, None if want == "none" else F.plain(want), name + field)

    def test_the_file_plots_each_value(self):
        text = F.e2e_figure(self.systems, self.sizes)
        for programs in F.e2e_rows(self.systems, self.sizes).values():
            for pword, *vals in programs:
                for v in vals:
                    if v is not None:
                        self.assertIn(f"({pword},{v})", text)
        self.assertEqual(text.count("\\nextgroupplot"), len(F.SYSTEMS) * len(self.sizes))
        self.assertEqual(text.count("\\legend{"), 1)

    def test_a_missing_floor_is_left_out_and_named(self):
        systems = copy.deepcopy(self.systems)
        program, pword, _ = F.PROGRAMS[0]
        systems["linux"]["floor"][F.cell_of(self.sizes[0])][program]["aa_largest_abs_d_ns"] = None
        text = F.e2e_figure(systems, self.sizes)
        self.assertIn(f"% Left out (missing): Linux, m={self.sizes[0]}, {pword}: floor.", text)


class Committed(unittest.TestCase):
    def test_the_committed_figures_are_current(self):
        for name, text in F.generate(SUMMARY, DESIGN, PLAN).items():
            self.assertEqual((OUT / name).read_text(encoding="utf-8"), text, name)

    def test_no_dash(self):
        for name, text in F.generate(SUMMARY, DESIGN, PLAN).items():
            self.assertIsNone(re.search("[–—]", text), name)


if __name__ == "__main__":
    unittest.main()
