# A fast HTTP route matcher with compile-time checks

Paper P2 of Alex Tsvetanov's PhD (see the Papers mono-repo).

A route matcher maps an HTTP request's method and path to a handler and the values captured
from the path. This paper reworks the author's RegexMatcher library into a route matcher,
RegexMatcher v2, and measures it against the route matchers of sixteen routers in C, C++, Rust
and Go, on the same route tables and the same queries. Literal-only methods get an exact-match
table and other methods a trie of path segments. A lookup allocates nothing, and a compile-time
front end rejects malformed patterns, mismatched handlers and duplicate routes. RegexMatcher v2
is published in its own repository, https://github.com/cpp-for-everything/RegexMatcher (release
2.1.0.0). This repository holds the benchmark, the minimal server, the analysis and the paper.

## Layout

- `bench/`    rbench, the lookup benchmark: its arms, its build, its run scripts, and its
              sanitizer records and gates
- `server/`   the minimal HTTP/1.1 server of H5(c) and H6, one binary with three router arms
- `t1/`       the H6 tools: the targets, the T1 run, and the server's sanitizer records and gate
- `tools/`    a check of answers for the processes whose agreement pass stopped at its budget
- `analysis/` scripts that turn the raw runs into `results/round2/`, with their tests
- `results/round2/` the tables, `summary.json` and the two generated macro files of the paper;
              its README lists the runs, their archives and the commands
- `results/`  files of round 1 (below)
- `design/round2/` the design notes of round 2, with their revision logs
- `paper/`    LaTeX source, figures and the text check (`check_text.py`)
- `hypotheses-round2.md` the pre-specification, frozen on 2026-09-30 before the run, with its
              revision log

## Round 1

The paper reports round 2. An earlier round, round 1, measured a pre-release of the same lookup
code inside another code base. It is development data, and none of its numbers is reported
(`hypotheses-round2.md`, section 1). Its frozen hypotheses (`hypotheses.md`), its frozen design
note (`design/router-v2.md`), the description of its run (`results/README.md`) and the result
files that name the other code base are archived privately and are not in this repository.
Comments in some sources and notes still refer to those files. The other files of round 1 in
`results/` are kept as they were.

The repository's earlier history is archived privately; `PROVENANCE.md` maps the commits that
the paper, the results and the sanitizer records cite to this history.

## Licence

Copyright 2026 Alex I. Tsvetanov.

This repository is licensed under the Apache License, Version 2.0. The full text is in
`LICENSE`. The licence covers every file except the manuscript (the LaTeX and BibTeX sources in
`paper/`, the figures in `paper/fig/`, and every PDF or Word copy built from them) and the
third-party files that `NOTICE` lists: the MDPI template files in `paper/Definitions/`, the
vendored chi and gin sources under `bench/arms/go/`, and the licence texts in `bench/data/`.
`NOTICE` also names the code in covered files that comes from other projects, with its licence,
and states that `bench/arms/ablation/route_r1.hpp`, a copy of RegexMatcher code, is licensed
here under the Apache License, Version 2.0 by its sole author.
