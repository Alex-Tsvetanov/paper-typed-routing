#!/usr/bin/env python3
"""Tests of analysis/stats.py, the statistics of round 2 (hypotheses-round2.md, section 3.4).

    python analysis/test_stats.py        (or: python -m pytest analysis/test_stats.py)

The oracles are exact values stated in the design (design/round2/hypotheses-v2-proposal.md,
section 5) or computed here by hand, never values the code under test printed:
1. The exact one-sided sign test at R = 16: 2^-16 for no pair at or above the margin,
   17/65536 = 2.59e-4 for one, 137/65536 = 2.09e-3 for two, 697/65536 = 1.06e-2 for three;
   H7's rule needs 13 of 16 pairs below 1.02 at one-sided 0.025 (12 of 16 gives 2517/65536).
   A ratio equal to the margin is not below it.
2. Holm's step-down over H1's 35 cells at 0.025 (first threshold 0.025/35 = 7.14e-4): one pair
   above the margin in every cell lets all 35 pass; two pairs above, up to 11 cells when the
   others are smaller; three pairs above, up to 2.
3. The normal functions without SciPy agree with known values (Phi(1.959964) = 0.975).
4. The clustered bootstrap with every pair its own cluster is round 1's bootstrap over pairs:
   the same resamples from the same generator, so the same estimate, distribution, z0 and
   acceleration.
5. Clusters are resampled whole: with two pairs per cluster, every resample holds whole
   clusters, and the jackknife leaves out one cluster at a time.
6. The BCa interval of a statistic with no spread is that value; bounds are ordered.
7. The fastest competitor is chosen again in every resample.
Pure NumPy and the standard library.
"""

from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from holm import holm  # noqa: E402
from stats import (bca, bca_bound, clusters_of, fastest_ratio, ndtr, ndtri, p_value, sign_p,  # noqa: E402
                   sign_test)

ALPHA = 0.025


def test_sign_test_r16_oracles():
    margin = 1.02
    below = [1.0] * 16
    assert sign_p(16, 16) == Fraction(1, 2 ** 16)
    for above, want in ((0, Fraction(1, 65536)), (1, Fraction(17, 65536)), (2, Fraction(137, 65536)),
                        (3, Fraction(697, 65536)), (4, Fraction(2517, 65536))):
        ratios = below[:16 - above] + [1.05] * above
        x, p = sign_test(ratios, margin)
        assert x == 16 - above
        assert p == float(want), (above, p, float(want))
    # the design's rounded values
    assert f"{sign_test([1.0] * 15 + [1.1], margin)[1]:.2e}" == "2.59e-04"
    assert f"{sign_test([1.0] * 14 + [1.1] * 2, margin)[1]:.2e}" == "2.09e-03"
    assert f"{sign_test([1.0] * 13 + [1.1] * 3, margin)[1]:.2e}" == "1.06e-02"
    # H7: 13 of 16 below passes at 0.025, 12 of 16 does not
    assert sign_test([1.0] * 13 + [1.03] * 3, margin)[1] <= ALPHA
    assert sign_test([1.0] * 12 + [1.03] * 4, margin)[1] > ALPHA


def test_sign_test_tie_is_not_below():
    x, p = sign_test([1.02] * 16, 1.02)
    assert x == 0 and p == 1.0
    x, _ = sign_test([1.0199999] + [1.02] * 15, 1.02)
    assert x == 1


def test_holm_family_of_35():
    p1 = float(Fraction(17, 65536))
    p2 = float(Fraction(137, 65536))
    p3 = float(Fraction(697, 65536))
    p0 = float(Fraction(1, 65536))
    assert f"{ALPHA / 35:.2e}" == "7.14e-04"
    assert all(a <= ALPHA for a in holm([p1] * 35))
    # two pairs above in k cells, none above in the others
    for k, passes in ((11, True), (12, False)):
        adj = holm([p0] * (35 - k) + [p2] * k)
        assert all(a <= ALPHA for a in adj) is passes, k
    for k, passes in ((2, True), (3, False)):
        adj = holm([p0] * (35 - k) + [p3] * k)
        assert all(a <= ALPHA for a in adj) is passes, k
    # R = 10 could never pass: 2^-10 is above the first threshold
    assert 2 ** -10 > ALPHA / 35


def test_normal_functions():
    assert abs(ndtr(1.959963984540054) - 0.975) < 1e-12
    assert abs(ndtri(0.975) - 1.959963984540054) < 1e-9
    assert ndtr(0.0) == 0.5 and ndtri(0.5) == 0.0
    for p in (1e-6, 0.01, 0.3, 0.9, 1 - 1e-6):
        assert abs(ndtr(ndtri(p)) - p) < 1e-12


def synthetic(seed: int, pairs: int = 16, rivals: int = 3):
    rng = np.random.default_rng(seed)
    base = rng.uniform(40, 60, size=pairs)
    v2 = base * rng.normal(0.9, 0.02, size=pairs)
    riv = np.array([base * rng.normal(1.0 + 0.05 * c, 0.02, size=pairs) for c in range(rivals)])
    return v2, riv


def pair_level_reference(v2, riv, resamples, rng):
    """Round 1's bootstrap over pairs (analysis/h1_stats.py at a2db64a), inlined as the oracle."""
    p = v2.shape[-1]
    theta = float(fastest_ratio(v2, riv))
    idx = rng.integers(0, p, size=(resamples, p))
    theta_b = fastest_ratio(v2[idx], riv[:, idx])
    b = len(theta_b)
    share = (np.sum(theta_b < theta) + 0.5 * np.sum(theta_b == theta)) / b
    z0 = ndtri(min(max(share, 1.0 / (2 * b)), 1 - 1.0 / (2 * b)))
    jack = np.array([float(fastest_ratio(np.delete(v2, i), np.delete(riv, i, axis=-1))) for i in range(p)])
    u = jack.mean() - jack
    den = float((u ** 2).sum())
    a = float((u ** 3).sum()) / (6 * den ** 1.5) if den > 0 else 0.0
    return theta, theta_b, z0, a


def test_singleton_clusters_equal_pair_bootstrap():
    v2, riv = synthetic(1)
    got = bca(v2, riv, fastest_ratio, None, 2000, np.random.default_rng(7))
    want = pair_level_reference(v2, riv, 2000, np.random.default_rng(7))
    assert got.theta == want[0]
    assert np.array_equal(got.theta_b, want[1])
    assert abs(got.z0 - want[2]) < 1e-12 and abs(got.a - want[3]) < 1e-12
    singletons = list(range(16))
    got2 = bca(v2, riv, fastest_ratio, singletons, 2000, np.random.default_rng(7))
    assert np.array_equal(got2.theta_b, want[1]) and abs(got2.a - want[3]) < 1e-12


def test_clusters_resampled_whole():
    seeds = [111 + (k % 8) for k in range(16)]
    members = clusters_of(seeds)
    assert members.shape == (8, 2)
    for row in members:
        assert seeds[row[0]] == seeds[row[1]]
    # A statistic that reports, per resample, whether every table seed drawn appears with both of
    # its pairs: with whole clusters, it always does.
    probe = np.arange(16, dtype=float)

    def whole(v, _r):
        v = np.atleast_2d(v)
        ok = []
        for row in v:
            idx = row.astype(int)
            ok.append(all(np.sum(np.isin(idx, members[c])) % 2 == 0 for c in range(8)))
        out = np.array(ok, dtype=float)
        return out if v.shape[0] > 1 else out[0]

    res = bca(probe, probe[None, :], whole, seeds, 500, np.random.default_rng(3))
    assert np.all(res.theta_b == 1.0)
    assert len(res.jackknife) == 8


def test_no_spread_interval():
    v2 = np.full(16, 45.0)
    riv = np.full((2, 16), 50.0)
    seeds = [111 + (k % 8) for k in range(16)]
    res = bca(v2, riv, fastest_ratio, seeds, 1000, np.random.default_rng(5))
    assert res.theta == 0.9
    assert bca_bound(res, 0.025) == 0.9 and bca_bound(res, 0.975) == 0.9
    assert p_value(res, 1.02) < 1e-3


def test_bounds_ordered_and_p_monotone():
    v2, riv = synthetic(2)
    seeds = [111 + (k % 8) for k in range(16)]
    res = bca(v2, riv, fastest_ratio, seeds, 4000, np.random.default_rng(9))
    lo, hi = bca_bound(res, 0.025), bca_bound(res, 0.975)
    assert lo <= res.theta <= hi
    assert p_value(res, 1.02) <= p_value(res, 1.0) <= p_value(res, 0.9)


def test_fastest_chosen_per_resample():
    # rival 0 is faster in pairs 0 to 7, rival 1 in pairs 8 to 15, equal medians over all pairs
    v2 = np.full(16, 1.0)
    r0 = np.array([1.0] * 8 + [3.0] * 8)
    r1 = np.array([3.0] * 8 + [1.0] * 8)
    riv = np.array([r0, r1])
    idx = np.array([[0] * 16, [15] * 16])
    got = fastest_ratio(v2[idx], riv[:, idx])
    assert np.array_equal(got, np.array([1.0, 1.0]))


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok: {t.__name__}")
    print(f"{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
