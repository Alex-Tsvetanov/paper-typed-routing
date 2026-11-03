#!/usr/bin/env python3
"""Tests of t3/rr_macros.py: each macro comes from its source field (synthetic records, made-up counts that are no
result), a stale records.json is refused, the committed macros and tables are what the committed inputs give, no
macro name repeats round 2's, and no output holds a dash.

    python t3/test_rr_macros.py          (or: python -m pytest t3/test_rr_macros.py)
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import rr_macros as M  # noqa: E402
import rr_records as RR  # noqa: E402
import rr_results as R  # noqa: E402
from test_rr_records import timed  # noqa: E402
from test_rr_results import plan_dict, record  # noqa: E402

OUT = ROOT / "results" / "round3"
NAME = re.compile(r"\\newcommand\*?\{\\([A-Za-z]+)\}\{(.*)\}")
SETTINGS = {"window_s": 1.5, "warmup_s": 0.1, "server_warmup_s": 1.0, "connections": 64, "error_share_max": 0.001}


def macros_of(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).split("}  %")[0] for m in map(NAME.match, text.splitlines()) if m}


def three(arms: tuple, k: int = 1) -> dict:
    plan = plan_dict(arms * k if k > 1 else arms, arms * k if k > 1 else arms)
    plan["programs"].append({"name": "mserver-rs", "path": "mserver-rs", "arms": list(arms * k if k > 1 else arms)})
    return {**plan, **SETTINGS, "housekeeping_cpus": "0-1"}


OS = {"linux": "Linux-7.0.1-test-x86_64", "windows": "Windows-11-10.0.12345-SP0"}


def sessioned(rows: list[dict], system: str) -> list[dict]:
    rows[0] = {**rows[0], "os": OS[system], "cpu_model": "Test CPU with Radeon Graphics"}
    return rows


class Synthetic(unittest.TestCase):
    """Both systems' A/A, campaign and k-server records, their analysis files, records.json and the macros."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.plans, self.design = self.dir / "plans", self.dir / "design"
        self.plans.mkdir()
        self.design.mkdir()
        rr, aa, aak = three(("v2", "crow", "null")), three(("v2", "v2")), three(("v2",), 4)
        for s in ("L", "W"):
            for name, plan in ((f"rr-{s}.json", rr), (f"rr-aa-{s}.json", aa), (f"rr-aak-{s}.json", aak)):
                (self.plans / name).write_text(json.dumps(plan))
        self.plan = self.plans / "rr-W.json"
        jobs = []
        for system, letter in (("linux", "L"), ("windows", "W")):
            rows = {k: sessioned(timed(record(p, system=system)), system) for k, p in (("aa", aa), ("rr", rr), ("aak", aak))}
            jobs.append(self.job(f"job-{letter}", rows))
            an = {k: R.analyse(v, k) for k, v in rows.items()}
            an["floor"] = R.floor(an["aa"], an["rr"])
            self.wrap(f"floor-{letter}.json", f"job-{letter}", rows, {system: an})
        earlier = {k: sessioned(timed(record(p, system="windows")), "windows") for k, p in (("aa", aa), ("rr", rr))}
        jobs.append(self.job("job-early", earlier))
        self.wrap("rr-W.json", "job-early", earlier, {"windows": {k: R.analyse(v, k) for k, v in earlier.items()}})
        self.records = self.dir / "records.json"
        self.records.write_text(json.dumps(RR.build(
            [self.design / n for n in ("floor-W.json", "floor-L.json", "rr-W.json")], jobs, self.plans)))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def job(self, name: str, rows: dict) -> Path:
        d = self.dir / name
        (d / "out").mkdir(parents=True)
        for kind, r in rows.items():
            (d / "out" / f"{kind}.jsonl").write_text("\n".join(json.dumps(x) for x in r) + "\n")
        (d / "record.json").write_text(json.dumps({"start_state": {"uptime_s": 1000.0},
                                                   "command_start": "2026-01-02T03:00:00+02:00",
                                                   "command_end": "2026-01-02T03:10:00+02:00"}))
        return d

    def wrap(self, name: str, job: str, rows: dict, systems: dict) -> None:
        inputs = [{"job": job, "file": f"out/{k}.jsonl",
                   "sha256": hashlib.sha256((self.dir / job / "out" / f"{k}.jsonl").read_bytes()).hexdigest()}
                  for k in rows]
        (self.design / name).write_text(json.dumps({"inputs": inputs, "analysis": {"systems": systems}}))

    def generate(self) -> dict[str, str]:
        return macros_of(M.generate(self.design, self.records, self.plan)[0])


class FieldTests(Synthetic):
    def test_each_macro_comes_from_its_source_field(self) -> None:
        got = self.generate()
        an = json.loads((self.design / "floor-L.json").read_text())["analysis"]["systems"]["linux"]
        cell = "mixed-disjoint/m1000/t111"
        prog = an["rr"]["cells"][cell]["programs"]["mserver-rs"]
        floor = an["floor"][cell]["mserver-rs"]
        v2 = next(s for s in prog["contestants"] if s["arm"] == "v2")
        name = "RThreeLinuxRustThousand"
        self.assertEqual(got[f"{name}Floor"], M.num(floor["aa_largest_abs_d_ns"]))
        self.assertEqual(got[f"{name}Lead"], M.num(floor["neighbours"][0]["gap_ns"]))
        self.assertEqual(got[f"{name}RunnerUp"], "\\texttt{crow}")
        self.assertEqual(got[f"{name}VtwoNs"], M.num(v2["ns_per_request"]["median"]))
        self.assertEqual(got[f"{name}AheadOf"], "3")
        k = an["aak"]["cells"][cell]["programs"]["mserver-rs"]
        self.assertEqual(got[f"{name}KSpan"], M.num(k["medians_ns"]["range"]))
        self.assertEqual(got[f"{name}Clears"], "clears" if floor["neighbours"][0]["clears"] else "does not clear")
        self.assertEqual(got["RThreeLinuxAaValid"], str(len([r for r in record(three(("v2", "v2")))
                                                             if r.get("type") == "window"])))
        self.assertEqual(got["RThreeRounds"], "3")
        self.assertEqual((got["RThreeCpu"], got["RThreeLinuxKernel"], got["RThreeWindowsBuild"]),
                         ("Test CPU", "7.0.1", "12345"))
        self.assertEqual((got["RThreeServerCpu"], got["RThreeGenCpuFirst"], got["RThreeRunnerCpuLast"]), ("14", "2", "1"))

    def test_v2_that_is_not_first_raises(self) -> None:
        path = self.design / "floor-W.json"
        w = json.loads(path.read_text())
        w["analysis"]["systems"]["windows"]["rr"]["cells"]["mixed-disjoint/m1000/t111"]["programs"]["mserver"][
            "ranking"] = ["crow", "v2"]
        path.write_text(json.dumps(w))
        with self.assertRaisesRegex(ValueError, "v2 is not first"):
            self.generate()

    def test_a_records_json_of_other_inputs_is_refused_and_nothing_is_written(self) -> None:
        path = self.design / "floor-L.json"
        w = json.loads(path.read_text())
        w["inputs"][0]["sha256"] = "0" * 64
        path.write_text(json.dumps(w))
        out = self.dir / "out"
        with contextlib.redirect_stderr(io.StringIO()):
            rc = M.main(["--design", str(self.design), "--records", str(self.records), "--plan", str(self.plan),
                         "--out", str(out)])
        self.assertEqual(rc, 2)
        self.assertFalse(out.exists())


class FormatTests(unittest.TestCase):
    def test_a_negative_number_gets_a_math_minus_and_no_negative_zero(self) -> None:
        self.assertEqual(M.num(-14.84), "\\ensuremath{-}14.8")
        self.assertEqual(M.num(-0.04), "0.0")
        self.assertEqual(M.num(-1234.56), "\\ensuremath{-}1{,}234.6")
        self.assertEqual(M.num(None), "")
        self.assertEqual(M.mnum(None), "none")

    def test_the_settings_read_from_rr_w_are_rr_ls_too(self) -> None:
        w, l = (json.loads((HERE / "plans" / f"rr-{s}.json").read_text(encoding="utf-8")) for s in "WL")
        for key in ("rounds", "window_s", "warmup_s", "server_warmup_s", "connections", "others_max_pct",
                    "error_share_max", "sizes", "pairs"):
            self.assertEqual(w[key], l[key], key)


class RoundTwoTests(unittest.TestCase):
    """t3/round2_macros.py: round 2's paper macros without the desktop's numbers."""

    def test_the_committed_copy_is_current_and_holds_no_desktop_number(self) -> None:
        import round2_macros as R2
        src = (ROOT / "results" / "round2" / "macros-paper.tex").read_text(encoding="utf-8")
        text = R2.convert(src)
        self.assertEqual((OUT / "round2-paper-macros.tex").read_text(encoding="utf-8"), text)
        got, orig = macros_of(text), macros_of(src)
        self.assertEqual(set(got) & (R2.DESKTOP | set(R2.COST_ROWS)), set())
        for old, new in R2.COST_ROWS.items():
            self.assertEqual(got[new].split(" & "), orig[old].split(" & ")[:R2.CLANG_COLUMNS])
        self.assertEqual(len(got), len(orig) - len(R2.DESKTOP))
        self.assertTrue(all(got[k] == v for k, v in orig.items() if k in got))

    def test_a_missing_desktop_macro_is_refused(self) -> None:
        import round2_macros as R2
        with self.assertRaisesRegex(ValueError, "not in the source"):
            R2.convert("\\newcommand{\\Foo}{1}\n")


class CommittedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.macros, cls.tables = M.generate(ROOT / "design" / "round3", OUT / "records.json", HERE / "plans" / "rr-W.json")

    def test_the_committed_outputs_are_what_the_committed_inputs_give(self) -> None:
        self.assertEqual((OUT / "macros.tex").read_text(encoding="utf-8"), self.macros)
        self.assertEqual({p.name for p in (OUT / "tables").iterdir()}, set(self.tables))
        for name, text in self.tables.items():
            self.assertEqual((OUT / "tables" / name).read_text(encoding="utf-8"), text, name)

    def test_no_name_repeats_round_2s(self) -> None:
        round2 = set()
        for f in ("macros.tex", "macros-paper.tex"):
            round2 |= set(macros_of((ROOT / "results" / "round2" / f).read_text(encoding="utf-8")))
        ours = list(macros_of(self.macros))
        self.assertEqual(len(ours), self.macros.count("\\newcommand"))
        self.assertTrue(all(n.startswith("RThree") for n in ours))
        self.assertEqual(round2 & set(ours), set())

    def test_no_output_holds_a_dash(self) -> None:
        for name, text in [("macros.tex", self.macros), *self.tables.items()]:
            for dash in ("--", "\u2013", "\u2014"):
                self.assertNotIn(dash, text, name)
            self.assertIsNone(re.search(r"[{&] ?-\d", text), name)   # a minus is \ensuremath{-}

    def test_the_cells_that_clear_agree_with_each_cells_verdict(self) -> None:
        got = macros_of(self.macros)
        verdicts = [v for k, v in got.items() if k.endswith("Clears")]
        self.assertEqual(len(verdicts), int(got["RThreeCells"]))
        self.assertEqual(verdicts.count("clears"), int(got["RThreeCellsClear"]))
        self.assertEqual(got["RThreeNotClearList"].count(" on "), len(verdicts) - int(got["RThreeCellsClear"]))

    def test_every_table_row_has_its_columns(self) -> None:
        widths = {"campaign": 9, "floor": 7, "kserver": 7}
        for name, text in self.tables.items():
            width = widths[name.removesuffix(".tex").split("-")[0]]
            for line in text.splitlines():
                if line.startswith("%") or line == "\\midrule":
                    continue
                self.assertTrue(line.endswith(" \\\\"), (name, line))
                self.assertEqual(line.count(" & ") + 1, width, (name, line))


if __name__ == "__main__":
    unittest.main(verbosity=1)
