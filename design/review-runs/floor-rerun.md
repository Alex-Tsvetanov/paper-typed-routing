# Plan: round 3's floor rule, frozen, on a fresh whole-server run (Grok r1 M1a)

Status: plan, not frozen. It is frozen by a commit that sets this line to "frozen at <commit>", after step 1 of
`README.md` and before the first record of the run. Later changes go into a revision log at the end, with reasons.

## Why

Round 3's floor rule (no rank claim between neighbours in a campaign's ranking whose gap is at most the A/A run's
largest |d|) was chosen after the first records of both systems were seen, and on Linux it judges the records it was
chosen on (`hypotheses-round3.md`, revision log of 2026-10-28; Papers `grok-r1-review.md` M1). This run applies the
same rule, fixed before any of its records, to a fresh run of the same campaign.

## The rule, frozen

Alex's answers on the A/A run (2026-10-28, via the coordinator), verbatim: "Largest, A/A redone" and "More A/A
servers". As `hypotheses-round3.md` records them and `t3/rr_results.py` at d063274 implements them:

- Per system, program and size, the floor is the A/A run's largest |d| over its rounds, d the difference of the two
  v2 processes' median ns per request in a round.
- No rank claim between neighbours in a campaign's ranking whose gap in median ns per request is at most that floor.
- v2's lead is its gap to the next router. "v2's lead exceeds the A/A floor" when that gap is larger than the floor.
- The k-server run (v2 seven times per program) is descriptive and outside the floor.

No other floor and no test is added. A different floor (a quantile, the k-server span) would be another choice made
after round 3's data, which Grok's rounds 2 and 3 accepted declining; a sign test was ruled out for round 3 (the
coordinator's note of 2026-10-28 in `STATE.md`) and is not part of what Alex approved here.

## What stays as round 3 ran it

- The binaries: `_build_commit` 3ff814e50 and the `_expect_sha256` of `t3/plans/rr-*.json`; the round-3 sanitizer
  records cover them, so no new record is needed.
- The programs, routers, shape (mixed-disjoint), sizes (1,000 and 100,000), window (1.5 s after a 0.1 s lead-in),
  server warm-up, connections, CPU placement, guards, reruns of host-spoiled rounds, order seed and R = 7 rounds. R
  stays at 7 because the floor is the largest of R values: another R would change what the rule means.
- The job layout: on each system one job with the A/A run first and the campaign after it (`t3/jobs/rr.py`), and one
  k-server job (`t3/jobs/aa.py`); Windows' jobs start at least 15 min after boot.

## What changes

- **The seed pair: (127, 227).** No run has used it: round 2's lookup grid and round 3's pilot used pairs 111 to 126,
  and round 3's campaign (111, 211). Its request sets are made by `t3/make_requests.py` with the pair list extended,
  their rows added to `t3/requests-manifest.tsv` before the freeze, and made again and checked against the manifest
  on each system before its job. If the sets cannot be made identical on both systems, the pair is (112, 212), which
  has only v2-against-v2 pilot windows and no competitor window; the freeze names the pair.
- **The plans:** `t3/plans/rr2-aa-L.json`, `rr2-L.json`, `rr2-aak-L.json` and the same for W: round 3's plans with
  the new pair, nothing else changed (a test compares them key by key).
- **The analysis:** `t3/rr_results.py` and `t3/rr_macros.py` take the plan set and the pair as parameters (today six
  fixed plan names and `t111`); round 3's outputs stay byte for byte the same (tests), and this run's go to
  `results/rerun/` with macros under their own prefix.
- **The probe's source check leaves out one file that no build reads.** `t3/jobs/probe.py` refuses when a compiled
  source changed since the plan's build commit. 0d6b22f changed `bench/ct_msvc.py` (H7's MSVC cost script, a
  `--msvc-version` argument) after round 3's bring-up, so the check would refuse round 3's own binaries. It now
  leaves out that one file (`NOT_COMPILED`; a test finds no CMake file that names it). Every other compiled path is
  compared as before, and every binary's sha256 is checked as before.

## What the paper reports

- The fresh run's count of cells where v2's lead exceeds the A/A floor leads, whatever it is. Round 3's count is
  reported beside it as the run that chose the rule.
- Per cell: the medians, v2's lead, the floor, the k-server span, as round 3 reports them. Every router's rank and
  neighbour gaps as the rule gives them. Nothing is dropped or run again except as round 3's own rules say (a
  host-spoiled round once).
- Known risk, stated now: in round 3 the first seconds of a Windows job after idle ran slow, and two Windows floors
  came from that round. The design keeps round 3's layout, so the same may happen; it is reported as the rule gives it.

## Laptop hours

Request sets at most 853 s (Linux) and 2,034 s (Windows); the A/A run and campaign 788 s and 922 s; the k-server run
564 s and 624 s; Windows' wait after boot 900 s. About 2 h in all (`README.md`).
