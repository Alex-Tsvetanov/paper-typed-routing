# Manuscript revision log

The hypothesis text in `hypotheses-round2.md` is not edited. The schedule note records the
venue change in its revision log only. This note records the manuscript.

## 2026-10-22. Journal of Systems and Software

The manuscript class and front matter now target the Journal of Systems and Software
(`elsarticle`, preprint, author-year). Future Internet stays a fallback, and only after the
Journal of Systems and Software and Software: Practice and Experience both reject the paper.
The title is no longer a ranking headline.

### The external-router end-to-end block is absent

The Cursor brief requires end-to-end latency against the external routers, at the same table
sizes as the lookup grid, with an interval. That block is not in this manuscript.

- The archived H6 run is `results/round2/h6.csv`, from
  `p2-raw-2026-09-30-L-h6.tar.gz`. Its columns are v1, v2 and the null router.
- The server selects `--router v2|v1|null` (`server/src/main.cpp`). gin, matchit and the other
  external routers are not arms of that server.
- No archive in `results/` records an end-to-end comparison against those routers.
- This session did not produce a new run. A citable number needs a green sanitizer gate on the
  measured sources, and the pre-registered procedure. This Windows host has no `10.10.10.1`
  address. A loopback timing without that gate would not be a result, so none was written.
- The manuscript states the gap in the results section "End to End Against the External
  Routers". It does not fill the block with the v1-versus-v2 server result. H6 still reports
  that server comparison, and it says the comparison says nothing about the competitors.

Threats to validity is its own section. The items are the existing design: one host, one
compiler per language, the native instruction set, loopback, the minimal server, the Drogon
transcription, the gin shim, the repeated ring, and the cut for slow arms. Two items make
explicit what the methods and the appendix already say: the external-router end-to-end block
is absent, and the C, C++, Rust and Go calls do not share one measurement boundary.

### What still blocks a Journal of Systems and Software submission

- The mandatory end-to-end block against the external routers has no measured result.
- The data-availability statement still marks the repository DOI and the release DOI as
  waiting on the author's accounts (a Zenodo record at the measured commit).
- The generative-AI declaration names Cursor agents in the journal's required form. The author
  confirms that wording before submission.
- The vitae is only the affiliation and the fact of this measurement. The author replaces it
  with the biography he wants on the submission form.
- A second publication campaign, on the Windows desktop, is still waiting. The numbers in the
  manuscript are the Linux campaign.
- The graphical abstract is optional and is not included.
