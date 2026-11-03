# Round 3 results

The files here are generated; nothing is edited by hand. The paper's round 3 numbers come from `macros.tex` and
the table bodies in `tables/` only.

| File | Written by | From |
|---|---|---|
| `records.json` | `t3/rr_records.py` | the round-robin records named, with their sha256, in `design/round3/floor-L.json`, `floor-W.json` and `rr-W.json` |
| `macros.tex` | `t3/rr_macros.py` | `design/round3/floor-L.json`, `floor-W.json` (written by `t3/rr_results.py`), `records.json`, `t3/plans/rr-W.json` |
| `tables/*.tex` | `t3/rr_macros.py` | the same; each file's first lines name its columns |
| `ct-msvc.json` | `t3/ct_msvc_results.py` | H7's MSVC costs on the laptop's Windows: the job's `tables.jsonl`, with the archive's and the file's sha256 |
| `round2-paper-macros.tex` | `t3/round2_macros.py` | round 2's `macros-paper.tex` without the desktop's numbers, plus H5(c)'s evidence from the minimal server's records |
| `figures/*.tex` | `t3/paper_figures.py` | `results/round2/summary.json` (H1's lookup grid) and `design/round3/floor-L.json`, `floor-W.json` (lead, floor, k-span); pgfplots pictures, described in `figures/README.md` |

To regenerate, unpack each job's archive into a folder named by the job (the archives and their sha256 are listed in
the `inputs` of the three analysis files), then:

    python t3/rr_records.py --analysis design/round3/floor-W.json --analysis design/round3/floor-L.json \
        --analysis design/round3/rr-W.json --jobs <job folders> --out results/round3/records.json
    python t3/rr_macros.py

`t3/test_rr_macros.py` checks that the committed `macros.tex` and `tables/` are what the committed inputs give.
`t3/test_paper_figures.py` checks the same of `figures/`, and that every plotted value equals its macro
(`python t3/paper_figures.py` regenerates them).
`t3/rr_records.py` refuses a record whose sha256 differs from the one listed.
