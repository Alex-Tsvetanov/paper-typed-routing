#!/usr/bin/env python3
"""Tests of t3/make_requests.py's pair list and t3/jobs/sets.py's check, install and recheck, on synthetic cells:
every file and digest below is made up for the test. No e2e_requests runs.

    python t3/test_sets.py          (or: python -m pytest t3/test_sets.py)
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "jobs"))
sys.path.insert(0, str(HERE))
import make_requests  # noqa: E402
import sets  # noqa: E402

HEADER = ("shape\tm\ttable_seed\tring_seed\ttable_digest\tring_digest\troutes_sha256\tring_sha256\t"
          "ring_expect_sha256\tall_sha256\tall_expect_sha256")
CELLS = [("mixed-disjoint", 1000, 127), ("mixed-disjoint", 100000, 127)]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def make_cell(root: Path, cell: tuple, salt: str = "", with_all: bool = True) -> str:
    """Write a made-up cell under root and return its manifest row."""
    shape, m, table = cell
    d = make_requests.cell_dir(root, shape, m, table)
    d.mkdir(parents=True, exist_ok=True)
    texts = {"routes.txt": f"GET /{m}/{salt}\n", "ring.txt": f"/{m}\n", "ring.expect": "0\n"}
    if with_all:
        texts.update({"all.txt": f"/{m}/all\n", "all.expect": "0\n"})
    for name, text in texts.items():
        (d / name).write_bytes(text.encode())
    digest = {k: sha(texts[name]) if name in texts else "-" for name, k in sets.FILES.items()}
    return "\t".join([shape, str(m), str(table), "227", "t" * 64, "r" * 64, digest["routes_sha256"],
                      digest["ring_sha256"], digest["ring_expect_sha256"], digest["all_sha256"],
                      digest["all_expect_sha256"]])


class PairListTests(unittest.TestCase):
    def test_a_pair_list_parses_and_bad_ones_are_refused(self) -> None:
        self.assertEqual(make_requests.parse_pairs("127:227"), [(127, 227)])
        self.assertEqual(make_requests.parse_pairs("127:227, 128:228"), [(127, 227), (128, 228)])
        for bad in ("127", "127:", "a:227", "0:227", "127:227,127:228", "127-227"):
            with self.assertRaises(ValueError, msg=bad):
                make_requests.parse_pairs(bad)

    def test_the_default_pairs_are_round_2s_sixteen(self) -> None:
        self.assertEqual(make_requests.PAIRS, tuple((111 + k, 211 + k) for k in range(16)))

    def test_the_committed_manifest_has_the_rerun_pairs_cells_as_round_3s_pair_has_its_own(self) -> None:
        header, rows = sets.read_manifest(HERE / "requests-manifest.tsv")
        self.assertEqual(header, HEADER)
        keys = header.split("\t")
        for m in (1000, 100000):
            new = dict(zip(keys, rows[("mixed-disjoint", m, 127)].split("\t")))
            old = dict(zip(keys, rows[("mixed-disjoint", m, 111)].split("\t")))
            self.assertEqual(new["ring_seed"], "227")
            self.assertEqual([new[k] == "-" for k in keys], [old[k] == "-" for k in keys])  # all.txt where 111 has it
        self.assertEqual(len(rows), 162)
        self.assertEqual(sorted(c for c in rows if c[2] == 127), sorted(CELLS))


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.generated, self.root = self.dir / "gen", self.dir / "root"
        self.old_row = make_cell(self.root, ("mixed-disjoint", 1000, 111))
        self.rows = [make_cell(self.generated, c) for c in CELLS]
        self.committed = self.dir / "committed.tsv"
        self.committed.write_text("\n".join([HEADER, self.old_row, *self.rows]) + "\n")
        (self.generated / "manifest.tsv").write_text("\n".join([HEADER, *self.rows]) + "\n")
        (self.root / "manifest.tsv").write_text("\n".join([HEADER, self.old_row]) + "\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def manifest(self) -> list[str]:
        return (self.root / "manifest.tsv").read_text().splitlines()


class InstallTests(Fixture):
    def test_check_install_and_recheck_add_the_cells_beside_the_old_ones(self) -> None:
        sets.check(self.generated / "manifest.tsv", self.committed, CELLS)
        got = sets.install(self.generated, self.root, self.committed, CELLS)
        self.assertEqual(got, {"mixed-disjoint/1000/127": {"cell": "copied", "row": "added"},
                               "mixed-disjoint/100000/127": {"cell": "copied", "row": "added"}})
        self.assertEqual(self.manifest(), [HEADER, self.old_row, *self.rows])
        with redirect_stdout(io.StringIO()):
            sets.recheck(self.root, self.committed, CELLS)
        again = sets.install(self.generated, self.root, self.committed, CELLS)   # a second run changes nothing
        self.assertEqual({w["cell"] for w in again.values()} | {w["row"] for w in again.values()}, {"present"})
        self.assertEqual(self.manifest(), [HEADER, self.old_row, *self.rows])

    def test_a_generated_row_that_is_not_committed_is_refused(self) -> None:
        (self.generated / "manifest.tsv").write_text("\n".join([HEADER, self.rows[0], self.rows[1][:-1] + "0"]) + "\n")
        with self.assertRaisesRegex(sets.SetsError, "not the committed rows"):
            sets.check(self.generated / "manifest.tsv", self.committed, CELLS)
        (self.generated / "manifest.tsv").write_text("\n".join([HEADER, self.rows[0]]) + "\n")
        with self.assertRaisesRegex(sets.SetsError, "the plan's are"):
            sets.check(self.generated / "manifest.tsv", self.committed, CELLS)

    def test_a_cell_there_that_differs_is_refused_and_nothing_changes(self) -> None:
        make_cell(self.root, CELLS[1], salt="other")
        before = self.manifest()
        with self.assertRaisesRegex(sets.SetsError, "differs from the committed row"):
            sets.install(self.generated, self.root, self.committed, CELLS)
        self.assertEqual(self.manifest(), before)
        self.assertFalse(make_requests.cell_dir(self.root, *CELLS[0]).exists())

    def test_another_row_for_the_cell_is_refused_and_nothing_is_copied(self) -> None:
        other = make_cell(self.dir / "elsewhere", CELLS[0], salt="other")
        (self.root / "manifest.tsv").write_text("\n".join([HEADER, self.old_row, other]) + "\n")
        with self.assertRaisesRegex(sets.SetsError, "another row"):
            sets.install(self.generated, self.root, self.committed, CELLS)
        self.assertFalse(make_requests.cell_dir(self.root, *CELLS[1]).exists())

    def test_a_data_root_without_its_manifest_is_refused(self) -> None:
        (self.root / "manifest.tsv").unlink()
        with self.assertRaisesRegex(sets.SetsError, "bring-up makes it"):
            sets.install(self.generated, self.root, self.committed, CELLS)

    def test_recheck_finds_a_changed_file_and_a_missing_committed_cell(self) -> None:
        sets.install(self.generated, self.root, self.committed, CELLS)
        f = make_requests.cell_dir(self.root, *CELLS[0]) / "ring.txt"
        f.write_text("/changed\n")
        with self.assertRaisesRegex(sets.SetsError, "differ from the committed rows"):
            sets.recheck(self.root, self.committed, CELLS)
        make_cell(self.root, CELLS[0])
        (self.root / "manifest.tsv").write_text("\n".join([HEADER, *self.rows]) + "\n")   # round 3's row lost
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                self.assertRaisesRegex(sets.SetsError, "every cell"):
            sets.recheck(self.root, self.committed, CELLS)

    def test_a_file_the_row_has_no_digest_for_is_a_problem(self) -> None:
        row = make_cell(self.dir / "noall", CELLS[0], with_all=False)
        d = make_requests.cell_dir(self.dir / "noall", *CELLS[0])
        self.assertEqual(sets.cell_problems(d, HEADER, row), [])
        (d / "all.txt").write_text("x\n")
        self.assertEqual(len(sets.cell_problems(d, HEADER, row)), 1)


class PlanTests(unittest.TestCase):
    def test_the_rerun_plans_name_the_rerun_pairs_cells(self) -> None:
        for s in "LW":
            plan = json.loads((HERE / "plans" / f"rr2-{s}.json").read_text(encoding="utf-8"))
            self.assertEqual(sets.cells_of(plan), CELLS)

    def test_the_sets_job_has_no_dashes(self) -> None:
        for name in ("jobs/sets.py", "test_sets.py", "make_requests.py"):
            text = (HERE / name).read_text(encoding="utf-8")
            self.assertNotIn(chr(0x2013), text, name)
            self.assertNotIn(chr(0x2014), text, name)


if __name__ == "__main__":
    unittest.main(verbosity=1)
