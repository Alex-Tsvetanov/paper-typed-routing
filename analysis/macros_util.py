"""Formatting and small helpers of analysis/macros.py: the rounding rule of every kind of
number, the macro store (names of letters only), cell names, and file readers. Kept apart so
that macros.py stays one file of sections; pure Python.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path


SHAPE_WORD = {"static": "Static", "param-last": "ParamLast", "param-first": "ParamFirst", "rest": "Rest",
              "wild": "Wild", "mixed-disjoint": "MixedDisjoint", "mixed-overlap": "MixedOverlap"}
UNVERIFIED = "not verified on every query"   # analysis/cells.py's failure text
SIZE_WORD = {10: "Ten", 100: "Hundred", 1000: "Thousand", 10000: "TenThousand", 100000: "HundredThousand"}

# ------------------------------------------------------------------------------ Rounding
# One function per kind of number. Half away from zero, on the shortest decimal form of the
# float, so a value prints as its digits suggest.

def fixed(x: float, places: int) -> str:
    q = Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return grouped(f"{q:f}")


def grouped(s: str) -> str:
    """Thousands separated by a LaTeX thin comma: 10{,}000."""
    sign, s = ("-", s[1:]) if s.startswith("-") else ("", s)
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        parts = []
        while len(whole) > 3:
            parts.insert(0, whole[-3:])
            whole = whole[:-3]
        whole = "{,}".join([whole] + parts)
    return sign + whole + ("." + frac if frac else "")


def ratio(x: float) -> str:
    """Ratios of times and their interval bounds: four decimals."""
    return fixed(x, 4)


def instructions(x: float) -> str:
    """Instructions per lookup: one decimal."""
    return fixed(x, 1)


def per_lookup(x: float) -> str:
    """Branch and cache misses per lookup: two decimals."""
    return fixed(x, 2)


def nanoseconds(x: float) -> str:
    """ns per lookup: one decimal."""
    return fixed(x, 1)


def milliseconds(seconds: float) -> str:
    """Build times, given in seconds, shown in ms to three significant figures."""
    v = seconds * 1e3
    places = max(0, 2 - math.floor(math.log10(abs(v)))) if v else 0
    return fixed(v, places)


def significant(x: float, digits: int = 3) -> str:
    """Large multiples (how many times slower the current router is): three significant figures."""
    places = max(0, digits - 1 - math.floor(math.log10(abs(x)))) if x else 0
    return fixed(round(x, digits - 1 - math.floor(math.log10(abs(x)))) if x else 0, places)


def multiple(x: float) -> str:
    """Multiples (heap bytes against a competitor's) and clock rates: two decimals."""
    return fixed(x, 2)


def percent(share: float) -> str:
    """A share as a whole percentage."""
    return fixed(100 * share, 0)


def count(n: int | float) -> str:
    return grouped(str(int(n)))


def power_bound(x: float) -> str:
    """The exponent of the smallest power of ten above |x| (x = 3.8e-14 gives -13)."""
    return str(math.floor(math.log10(abs(x))) + 1)


def scientific(x: float) -> str:
    """Math-mode a.b x 10^e, for p-values."""
    e = math.floor(math.log10(abs(x)))
    return f"{fixed(x / 10 ** e, 1)}\\times10^{{{e}}}"


# ------------------------------------------------------------------------------ Macros

class Macros:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []
        self.names: set[str] = set()

    def add(self, name: str, value: str, note: str = "") -> None:
        if not re.fullmatch(r"[A-Za-z]+", name):
            raise ValueError(f"macro name {name!r} is not letters only")
        if name in self.names:
            raise ValueError(f"macro {name} defined twice")
        self.names.add(name)
        self.items.append((name, value, note))

    def text(self) -> str:
        out = []
        for name, value, note in self.items:
            out.append(f"\\newcommand{{\\{name}}}{{{value}}}" + (f"  % {note}" if note else ""))
        return "\n".join(out) + "\n"


def cell_word(shape: str, m: int) -> str:
    return SHAPE_WORD[shape] + SIZE_WORD[m]


def tt(name: str) -> str:
    return f"\\texttt{{{name}}}"


def listing(items: list[str]) -> str:
    """a, b and c."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def cell_text(shape: str, m: int) -> str:
    return f"{tt(shape)} at $m={count(m)}$"


# ------------------------------------------------------------------------------ Inputs

def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("{")]


def key_values(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.partition(": ")
        if sep:
            out[k.strip()] = v.strip()
    return out


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    keys: list[str] = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def fnum(v: str) -> float | None:
    return float(v) if v not in ("", None) else None


def is_true(v: str) -> bool:
    return str(v) == "True"


def only_unverified(failures: str) -> bool:
    """A cell whose every failure is a process not verified on every query."""
    parts = [f for f in failures.split("; ") if f]
    return bool(parts) and all(UNVERIFIED in f for f in parts)


def rows_by(rows: list[dict], *keys: str) -> dict:
    out = defaultdict(list)
    for r in rows:
        out[tuple(r[k] for k in keys)].append(r)
    return out


def pair(r: dict) -> tuple:
    return (r.get("table_seed"), r.get("ring_seed"))
