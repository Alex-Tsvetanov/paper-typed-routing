"""The statistics of round 2 (hypotheses-round2.md, section 3.4; design/round2/hypotheses-v2-proposal.md).

A comparison of arms in a cell is paired by seed pair: the statistic is the median over the pairs
of a per-pair ratio (for H1, against the competitor with the lowest median over the pairs used,
chosen again in every resample). Two computations, both pre-specified:

- The BCa interval (Efron 1987), as round 1 computed it over pairs (analysis/h1_stats.py at
  a2db64a, checked against scipy.stats.bootstrap in lab/evidence/2026-09-27-L-bca-scipy-check),
  here generalized to clusters: `clusters` gives each pair's cluster (its table seed); a resample
  draws as many clusters as there are, with replacement, and keeps each drawn cluster's pairs
  together (an arm's values of a pair travel together too). The bias correction z0 counts ties
  as half; the acceleration comes from the jackknife over clusters. With every pair its own
  cluster (or clusters=None) this is exactly round 1's bootstrap over pairs, draw for draw.
  The one-sided p-value of H0 "theta >= margin" inverts the BCa upper bound: it is the level at
  which the upper bound equals the margin (round 1's formula).
- The exact sign test: X is the number of pairs whose ratio is below the margin (a ratio equal
  to the margin is not below it); under H0 "the median ratio is at least the margin", X is
  binomial with n pairs and 1/2 at the boundary; p = P(X >= x), computed exactly.

The normal distribution comes from Python's statistics.NormalDist, so no SciPy is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from math import comb
from statistics import NormalDist
from typing import Callable, Sequence

import numpy as np

_N = NormalDist()


def ndtr(x: float) -> float:
    """The standard normal distribution function."""
    return _N.cdf(float(x))


def ndtri(p: float) -> float:
    """Its inverse, for 0 < p < 1."""
    return 0.0 if p == 0.5 else _N.inv_cdf(float(p))


def sign_p(x: int, n: int) -> Fraction:
    """P(X >= x) for X binomial with n trials and probability 1/2, exactly."""
    return Fraction(sum(comb(n, k) for k in range(max(x, 0), n + 1)), 2 ** n)


def sign_test(ratios: Sequence[float], margin: float) -> tuple[int, float]:
    """(x, p): the number of ratios below the margin, and the exact one-sided p-value of H0
    "the median ratio is at least the margin"."""
    x = sum(1 for r in ratios if r < margin)
    return x, float(sign_p(x, len(ratios)))


def fastest_ratio(v2: np.ndarray, rivals: np.ndarray) -> np.ndarray:
    """v2: (..., P); rivals: (C, ..., P). The median over pairs of v2 over the rival with the lowest
    median, per leading index (round 1's statistic). With one rival: the median per-pair ratio."""
    med = np.median(rivals, axis=-1)
    best = np.argmin(med, axis=0)
    chosen = np.take_along_axis(rivals, np.asarray(best)[None, ..., None], axis=0)[0]
    return np.median(v2 / chosen, axis=-1)


def clusters_of(labels: Sequence) -> np.ndarray | list[np.ndarray]:
    """The pair indices of each cluster, clusters in sorted label order: a (K, s) array when every
    cluster has s pairs, else a list of arrays."""
    groups: dict = {}
    for i, lab in enumerate(labels):
        groups.setdefault(lab, []).append(i)
    members = [np.array(groups[k], dtype=int) for k in sorted(groups)]
    sizes = {len(m) for m in members}
    return np.array(members) if len(sizes) == 1 else members


@dataclass
class Boot:
    theta: float
    theta_b: np.ndarray
    z0: float
    a: float
    jackknife: list[float] = field(default_factory=list)
    clusters: int = 0


Stat = Callable[[np.ndarray, np.ndarray], np.ndarray]


def mid_share(values: np.ndarray, x: float) -> float:
    return float((np.sum(values < x) + 0.5 * np.sum(values == x)) / len(values))


def bca(v2: np.ndarray, rivals: np.ndarray, stat: Stat, clusters: Sequence | None, resamples: int,
        rng: np.random.Generator) -> Boot:
    """The estimate, the bootstrap distribution, z0 and the acceleration. clusters: each pair's
    cluster label (None: every pair its own cluster)."""
    v2 = np.asarray(v2, dtype=float)
    rivals = np.asarray(rivals, dtype=float)
    p = v2.shape[-1]
    theta = float(stat(v2, rivals))
    members = clusters_of(range(p) if clusters is None else list(clusters))
    k = len(members)
    if isinstance(members, np.ndarray):
        drawn = rng.integers(0, k, size=(resamples, k))
        idx = members[drawn].reshape(resamples, -1)
        theta_b = np.asarray(stat(v2[idx], rivals[:, idx]), dtype=float)
    else:
        draws = rng.integers(0, k, size=(resamples, k))
        theta_b = np.array([float(stat(v2[np.concatenate([members[c] for c in row])],
                                       rivals[:, np.concatenate([members[c] for c in row])])) for row in draws])
    b = len(theta_b)
    z0 = ndtri(min(max(mid_share(theta_b, theta), 1.0 / (2 * b)), 1 - 1.0 / (2 * b)))
    jack = []
    for c in range(k):
        keep = np.setdiff1d(np.arange(p), members[c])
        jack.append(float(stat(v2[..., keep], rivals[..., keep])))
    u = np.mean(jack) - np.array(jack)
    den = float((u ** 2).sum())
    a = float((u ** 3).sum()) / (6 * den ** 1.5) if den > 0 else 0.0
    return Boot(theta, theta_b, z0, a, jack, k)


def bca_bound(res: Boot, level: float) -> float:
    """The BCa quantile at `level` (0.975: the upper bound of the two-sided 95% interval)."""
    z = ndtri(level)
    q = ndtr(res.z0 + (res.z0 + z) / (1 - res.a * (res.z0 + z)))
    return float(np.quantile(res.theta_b, q))


def p_value(res: Boot, margin: float) -> float:
    """The one-sided p-value of H0 "theta >= margin", inverting the BCa upper bound; clipped so
    that no p is below about 1/(2B)."""
    b = len(res.theta_b)
    g = min(max(mid_share(res.theta_b, margin), 1.0 / (2 * b)), 1 - 1.0 / (2 * b))
    w = ndtri(g) - res.z0
    z = (w * (1 - res.a * res.z0) - res.z0) / (1 + res.a * w)
    return float(1 - ndtr(z))
