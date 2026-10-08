#!/usr/bin/env python3
"""The paper's figures, from the CSVs analysis/analyse.py writes (h1.csv and h7.csv of results/round2).

    figures.py [--results DIR] [--out paper/fig]

fig_h1.pdf: H1 per cell, RegexMatcher v2's time over the fastest competitor's (the median of the
per-pair ratios) with its 95% clustered BCa interval, grouped by shape, one mark per size, the
colour and marker naming the fastest competitor; the margin and 1 as reference lines; below it,
the cells at m = 10 on a linear scale, where the margin and 1 can be told apart. fig_h7.pdf: H7 per cell, the
compile-time table over the run-time one, the same way, with the cells whose whole interval lies
above 1 in a second hue. Needs matplotlib only (no SciPy), so it runs in any environment that
has the CSVs.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("pdf")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator  # noqa: E402

HERE = Path(__file__).resolve().parent
SHAPES = ["static", "param-last", "param-first", "rest", "wild", "mixed-disjoint", "mixed-overlap"]
MARGIN = 1.02                       # hypotheses-round2.md, H1 and H7
INK, MUTED, SERIES, PENDING = "#0b0b0b", "#52514e", "#2a78d6", "#8a8985"
TEXT_WIDTH_IN = 6.3                 # the article class's text width at 11 pt, near enough

plt.rcParams.update({"font.size": 8, "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7,
                     "legend.fontsize": 7, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK, "pdf.fonttype": 42,
                     "axes.spines.top": False, "axes.spines.right": False})


def read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def positions(rows: list[dict]) -> tuple[dict, list[float], list[str]]:
    """x of every (shape, m), grouped by shape with a gap between groups."""
    sizes = sorted({int(r["m"]) for r in rows})
    x, centres = {}, []
    for i, s in enumerate(SHAPES):
        base = i * (len(sizes) + 1)
        for j, m in enumerate(sizes):
            x[(s, m)] = base + j
        centres.append(base + (len(sizes) - 1) / 2)
    return x, centres, [str(int(math.log10(m))) for m in sizes]


MARKERS = {"gin": "o", "matchit": "s", "drogon": "^", "httprouter": "v", "nethttp": "P", "actix-router": "X",
           "crow": "D", "oatpp": "p", "pistache": "h", "boost-url": "*", "r3": "<", "uwebsockets": ">",
           "glaze": "d", "chi": "H", "path-tree": "8", "cpp-httplib": "1"}
ALERT = "#eb6834"                   # a second hue, for the H7 cells whose interval lies above 1


def frame(ax, x: dict, centres: list[float], size_labels: list[str], ylabel: str) -> None:
    ax.set_xticks([x[k] for k in sorted(x, key=x.get)])
    ax.set_xticklabels([size_labels[i % len(size_labels)] for i in range(len(x))])
    for c, s in zip(centres, SHAPES):
        ax.annotate(s.replace("mixed-", "mixed-\n"), (c, 0), xycoords=("data", "axes fraction"), xytext=(0, -13),
                    textcoords="offset points", ha="center", va="top", fontsize=7.5, family="monospace",
                    linespacing=1.0)
    ax.set_xlim(-0.8, max(x.values()) + 0.8)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("$k$ of each table size $m = 10^k$, grouped by shape", labelpad=26)
    ax.grid(axis="y", color="#e4e3df", lw=0.5, zorder=0)
    ax.tick_params(axis="x", length=0)


def series(ax, x: dict, rows: list[dict], marker: str, color: str, label: str, filled: bool = True) -> None:
    if not rows:
        return
    xs = [x[(r["shape"], int(r["m"]))] for r in rows]
    y = [float(r["ratio"]) for r in rows]
    lo = [float(r["ratio"]) - float(r["ci_low"]) for r in rows]
    hi = [float(r["ci_high"]) - float(r["ratio"]) for r in rows]
    ax.errorbar(xs, y, yerr=[lo, hi], fmt=marker, ms=2.6, color=color, ecolor=color, elinewidth=1.3, capsize=2.2,
                mfc=color if filled else "white", mew=0.9, zorder=3, label=label)


def finish(fig, ax, out: Path, ncol: int) -> None:
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=ncol, frameon=False, handletextpad=0.4,
              columnspacing=1.2)
    fig.subplots_adjust(left=0.1, right=0.99, top=0.86, bottom=0.3)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


# The fastest competitors of H1, in the reference categorical order (dataviz skill, palette.md,
# light mode; checked with its validator: all checks pass, contrast relieved by the marker shapes,
# the legend and Table 4). A competitor keeps its colour and marker in both panels.
FASTEST_STYLE = {"gin": ("#2a78d6", "o"), "matchit": ("#eb6834", "s"), "uwebsockets": ("#1baf7a", ">"),
                 "glaze": ("#eda100", "d")}
DISPLAY = {"uwebsockets": "uWebSockets", "nethttp": "net/http", "boost-url": "Boost.URL", "oatpp": "Oat++",
           "crow": "Crow", "drogon": "Drogon", "pistache": "Pistache"}


def style_of(arm: str) -> tuple[str, str]:
    return FASTEST_STYLE.get(arm, (SERIES, MARKERS.get(arm, "o")))


def draw_h1(rows: list[dict], out: Path) -> None:
    """Every cell on a log scale above, the cells at m = 10 on a linear scale below, where the margin
    and 1 are told apart. Colour and marker name the fastest competitor of the cell."""
    tested = [r for r in rows if r["status"] == "tested"]
    order = sorted({r["fastest"] for r in tested}, key=lambda a: -sum(r["fastest"] == a for r in tested))
    fig, (ax, low) = plt.subplots(2, 1, figsize=(TEXT_WIDTH_IN, 4.9), gridspec_kw={"height_ratios": [2.3, 1.35]})
    x, centres, size_labels = positions(rows)
    for arm in order:
        colour, marker = style_of(arm)
        series(ax, x, [r for r in tested if r["fastest"] == arm], marker, colour, f"fastest: {DISPLAY.get(arm, arm)}")
    ax.axhline(1.0, color=MUTED, lw=0.8, zorder=1, label="ratio 1.00")
    ax.axhline(MARGIN, color=INK, lw=0.9, ls=(0, (4, 3)), zorder=2, label=f"margin {MARGIN}")
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(FixedLocator([0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_locator(NullLocator())
    frame(ax, x, centres, size_labels, "v2 / fastest competitor")
    ax.set_xlabel("$k$ of each table size $m = 10^k$, grouped by shape", labelpad=26)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, frameon=False, handletextpad=0.4,
              columnspacing=1.2)
    # The cells at m = 10, linear scale.
    small = [r for r in tested if int(r["m"]) == 10]
    xs = {s: i for i, s in enumerate(SHAPES)}
    for arm in order:
        colour, marker = style_of(arm)
        mine = [r for r in small if r["fastest"] == arm]
        if not mine:
            continue
        low.errorbar([xs[r["shape"]] for r in mine], [float(r["ratio"]) for r in mine],
                     yerr=[[float(r["ratio"]) - float(r["ci_low"]) for r in mine],
                           [float(r["ci_high"]) - float(r["ratio"]) for r in mine]],
                     fmt=marker, ms=3.4, color=colour, ecolor=colour, elinewidth=1.3, capsize=2.2, zorder=3)
    low.axhline(1.0, color=MUTED, lw=0.8, zorder=1)
    low.axhline(MARGIN, color=INK, lw=0.9, ls=(0, (4, 3)), zorder=2)
    low.set_xticks(range(len(SHAPES)))
    low.set_xticklabels([s.replace("mixed-", "mixed-\n") for s in SHAPES], family="monospace", fontsize=7,
                        linespacing=1.0)
    low.set_xlim(-0.6, len(SHAPES) - 0.4)
    low.set_ylim(0.5, 1.12)
    low.yaxis.set_major_locator(FixedLocator([0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1]))
    low.set_ylabel("at $m = 10$")
    low.grid(axis="y", color="#e4e3df", lw=0.5, zorder=0)
    low.tick_params(axis="x", length=0)
    fig.subplots_adjust(left=0.1, right=0.99, top=0.9, bottom=0.08, hspace=0.6)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def draw_h7(rows: list[dict], out: Path) -> None:
    """A second hue for the cells whose whole interval lies above 1."""
    x, centres, size_labels = positions(rows)
    fig, ax = plt.subplots(figsize=(TEXT_WIDTH_IN, 2.7))
    tested = [r for r in rows if r["status"] == "tested"]
    series(ax, x, [r for r in tested if float(r["ci_low"]) <= 1], "o", SERIES, "median per-pair ratio, 95% BCa")
    series(ax, x, [r for r in tested if float(r["ci_low"]) > 1], "s", ALERT, "interval wholly above 1")
    ax.axhline(1.0, color=MUTED, lw=0.8, zorder=1)
    ax.axhline(MARGIN, color=INK, lw=0.9, ls=(0, (4, 3)), zorder=2, label=f"margin {MARGIN}")
    ax.set_ylim(top=max(ax.get_ylim()[1], MARGIN + 0.005))
    frame(ax, x, centres, size_labels, "compile-time / run-time table")
    finish(fig, ax, out, 3)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", type=Path, default=HERE.parent / "results/round2")
    ap.add_argument("--out", type=Path, default=HERE.parent / "paper/fig")
    a = ap.parse_args()
    draw_h1(read(a.results / "h1.csv"), a.out / "fig_h1.pdf")
    draw_h7(read(a.results / "h7.csv"), a.out / "fig_h7.pdf")
    print(f"figures: {a.out / 'fig_h1.pdf'}, {a.out / 'fig_h7.pdf'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
