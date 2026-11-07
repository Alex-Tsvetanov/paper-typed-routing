#!/usr/bin/env python3
"""Write, or check, the ablation copies of RegexMatcher v2's route headers (design/review-runs/ablations.md).

    make_ablation.py --regexmatcher DIR [--out-dir arms/ablation]
    make_ablation.py --regexmatcher DIR --check [--out-dir arms/ablation]

DIR is a RegexMatcher checkout or snapshot at the pinned commit (d1d73e99b). Each copy is the six
headers the run-time table and its lookup need (config, detail/words, pattern, table, lookup,
runtime_table, in that order) with their own includes dropped and the standard ones gathered at the
top, renamed to its own namespace (matcher::route_copy, matcher::route_ab_linear, ...) and macro
prefix (MATCHER_ROUTE_COPY_, ...), so that all of them link beside the pinned headers in one binary:

    route_copy.hpp        the renamed copy, no other change (the control)
    route_ab_linear.hpp   the copy and one change: kLinearEdges above any node's edge count
    route_ab_hashed.hpp   the copy and one change: kLinearEdges = 0
    route_ab_noexact.hpp  the copy and one change: no route goes to the exact-match table
    route_ab_bytes.hpp    the copy and one change: an edge's label compared a byte at a time
    route_ab_heapstack.hpp  the copy and one change: the walk's choice stack in a heap block, one per walk
    route_ab_strings.hpp  the copy and one change: a captured value owns a std::string copy of its bytes
                          (and the include of <string>, a second marked hunk)

Each change replaces one anchored block of the copy (the anchor must occur exactly once), and every
line it writes carries the mark "ablation (<arm>)". A variant may name further anchored blocks
(`extra`, used only by ab-strings for the include its type needs). The script checks, for each
variant, that the variant with its names mapped back to the copy's differs from the copy in exactly
one hunk per anchored block, and that every line the hunks add is marked. --check writes nothing and exits 1 if a file on disk differs from
what DIR gives (CRLF read as LF).
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

HEADERS = ("config.hpp", "detail/words.hpp", "pattern.hpp", "table.hpp", "lookup.hpp", "runtime_table.hpp")
OUT_DIR = Path(__file__).resolve().parent.parent / "arms" / "ablation"
INCLUDE = re.compile(r"^#include\s+(<[^>]+>|\"[^\"]+\")\s*$")
MARK = "ablation ("


@dataclass(frozen=True)
class Variant:
    arm: str        # the rbench arm
    tag: str        # namespace suffix and file name: route_<tag>.hpp, matcher::route_<tag>
    what: str       # the change, for the preamble
    anchor: str     # the block of the copy that the change replaces ("" for the copy)
    change: str     # what replaces it
    extra: tuple[tuple[str, str], ...] = ()  # further (anchor, change) blocks, each its own hunk


LINEAR_ANCHOR = "\t\tinline constexpr std::size_t kLinearEdges = 8;\n"
NOEXACT_ANCHOR = "\t\tstd::uint16_t param_methods = 0;  // bit m: some route of method m has a parameter\n"
BYTES_ANCHOR = (
    "\t\t\tconst auto matches = [&](const Edge& e) {\n"
    "\t\t\t\treturn e.word == word && e.len == seg.size() &&\n"
    "\t\t\t\t       (seg.size() <= 8 || same_from(t.arena.data() + e.off, seg.data(), seg.size(), 8));\n"
    "\t\t\t};\n")

HEAPSTACK_ANCHOR = "\t\t\tstd::array<Choice, kMaxSegments + 1> stack;  // trivial: never zeroed, only pushed and popped\n"
STRINGS_ANCHOR = (
    "\t// A captured value: a view into the path the lookup was given. Trivial on purpose, so\n"
    "\t// that the captures of a lookup are never zeroed at run time; only the first `count`\n"
    "\t// of them are ever set or read.\n"
    "\tstruct Capture\n"
    "\t{\n"
    "\t\tconst char* ptr;\n"
    "\t\tstd::size_t len;\n"
    "\n"
    "\t\tconstexpr std::string_view view() const noexcept { return {ptr, len}; }\n"
    "\t\tconstexpr operator std::string_view() const noexcept { return view(); }\n"
    "\t\tconstexpr const char* data() const noexcept { return ptr; }\n"
    "\t\tconstexpr std::size_t size() const noexcept { return len; }\n"
    "\t\tconstexpr bool empty() const noexcept { return len == 0; }\n"
    "\t\tfriend constexpr bool operator==(const Capture& a, std::string_view b) noexcept { return a.view() == b; }\n"
    "\t};\n")
STRINGS_INCLUDE_ANCHOR = "#include <string_view>\n"

VARIANTS = (
    Variant("regexmatcher-v2-copy", "copy", "none: the renamed copy itself, the control for every variant", "", ""),
    Variant("regexmatcher-v2-ab-linear", "ab_linear",
            "kLinearEdges above any node's edge count, so every node searches its edges linearly",
            LINEAR_ANCHOR,
            "\t\tinline constexpr std::size_t kLinearEdges = ~std::size_t{0};  "
            "// ablation (ab-linear): above any node's edge count, so no node is hashed\n"),
    Variant("regexmatcher-v2-ab-hashed", "ab_hashed",
            "kLinearEdges = 0, so every node with an edge is hashed",
            LINEAR_ANCHOR,
            "\t\tinline constexpr std::size_t kLinearEdges = 0;  "
            "// ablation (ab-hashed): every node with an edge is hashed\n"),
    Variant("regexmatcher-v2-ab-noexact", "ab_noexact",
            "every method counts as having a parameter route, so the routes of an all-literal method stay in its "
            "trie and the exact-match table is empty",
            NOEXACT_ANCHOR,
            "\t\tstd::uint16_t param_methods = 0xFFFF;  "
            "// ablation (ab-noexact): every method counts as having a parameter route: no exact-match table\n"),
    Variant("regexmatcher-v2-ab-bytes", "ab_bytes",
            "an edge's label compared with the segment a byte at a time, not as its first 8-byte word and then "
            "8-byte words, in the edge search of the walk (linear and hashed nodes); the word is still loaded, "
            "stored in each edge and hashed as before",
            BYTES_ANCHOR,
            "\t\t\t// ablation (ab-bytes) begin: the length, then the label a byte at a time (no word compare)\n"
            "\t\t\tconst auto matches = [&](const Edge& e) {  // ablation (ab-bytes)\n"
            "\t\t\t\tif (e.len != seg.size())  // ablation (ab-bytes)\n"
            "\t\t\t\t{  // ablation (ab-bytes)\n"
            "\t\t\t\t\treturn false;  // ablation (ab-bytes)\n"
            "\t\t\t\t}  // ablation (ab-bytes)\n"
            "\t\t\t\tconst char* label = t.arena.data() + e.off;  // ablation (ab-bytes)\n"
            "#pragma clang loop vectorize(disable) interleave(disable)  // ablation (ab-bytes): one byte per step\n"
            "\t\t\t\tfor (std::size_t i = 0; i < seg.size(); ++i)  // ablation (ab-bytes)\n"
            "\t\t\t\t{  // ablation (ab-bytes)\n"
            "\t\t\t\t\tif (label[i] != seg[i])  // ablation (ab-bytes)\n"
            "\t\t\t\t\t{  // ablation (ab-bytes)\n"
            "\t\t\t\t\t\treturn false;  // ablation (ab-bytes)\n"
            "\t\t\t\t\t}  // ablation (ab-bytes)\n"
            "\t\t\t\t}  // ablation (ab-bytes)\n"
            "\t\t\t\treturn true;  // ablation (ab-bytes)\n"
            "\t\t\t};  // ablation (ab-bytes)\n"
            "\t\t\t// ablation (ab-bytes) end\n"),
    Variant("regexmatcher-v2-ab-heapstack", "ab_heapstack",
            "the walk's choice stack is a heap block of the same kMaxSegments + 1 entries, allocated with new[] "
            "at the start of every walk and freed at its end (default-initialized, not zeroed), instead of an "
            "array in the walk's own frame; the pushes and pops are unchanged",
            HEAPSTACK_ANCHOR,
            (
            "\t\t\t// ablation (ab-heapstack) begin: the choice stack in a heap block, one allocation per walk\n"
            "\t\t\tstruct HeapStack  // ablation (ab-heapstack)\n"
            "\t\t\t{  // ablation (ab-heapstack)\n"
            "\t\t\t\tChoice* p = new Choice[kMaxSegments + 1];  // ablation (ab-heapstack): not zeroed\n"
            "\t\t\t\tconstexpr ~HeapStack() { delete[] p; }  // ablation (ab-heapstack)\n"
            "\t\t\t\tconstexpr Choice& operator[](std::size_t i) noexcept { return p[i]; }  // ablation (ab-heapstack)\n"
            "\t\t\t} stack;  // ablation (ab-heapstack)\n"
            "\t\t\t// ablation (ab-heapstack) end\n")),
    Variant("regexmatcher-v2-ab-strings", "ab_strings",
            "a captured value owns a std::string copy of its bytes instead of a view (pointer and length) into "
            "the path, so every capture the walk takes copies its segment, every Match constructs and destroys "
            "its kMaxParams strings and a Match is copied deeply; the walk's own lines are unchanged; the "
            "include of <string> is a second marked hunk",
            STRINGS_ANCHOR,
            (
            "\t// ablation (ab-strings) begin: a captured value owns a copy of its bytes, not a view into the path\n"
            "\tstruct Capture  // ablation (ab-strings)\n"
            "\t{  // ablation (ab-strings)\n"
            "\t\tstd::string s;  // ablation (ab-strings)\n"
            "\t\tconstexpr Capture() = default;  // ablation (ab-strings)\n"
            "\t\tconstexpr Capture(const char* p, std::size_t n) : s(p, n) {}  // ablation (ab-strings)\n"
            "\t\tconstexpr std::string_view view() const noexcept { return s; }  // ablation (ab-strings)\n"
            "\t\tconstexpr operator std::string_view() const noexcept { return view(); }  // ablation (ab-strings)\n"
            "\t\tconstexpr const char* data() const noexcept { return s.data(); }  // ablation (ab-strings)\n"
            "\t\tconstexpr std::size_t size() const noexcept { return s.size(); }  // ablation (ab-strings)\n"
            "\t\tconstexpr bool empty() const noexcept { return s.empty(); }  // ablation (ab-strings)\n"
            "\t\tfriend constexpr bool operator==(const Capture& a, std::string_view b) noexcept  // ablation (ab-strings)\n"
            "\t\t{  // ablation (ab-strings)\n"
            "\t\t\treturn a.view() == b;  // ablation (ab-strings)\n"
            "\t\t}  // ablation (ab-strings)\n"
            "\t};  // ablation (ab-strings)\n"
            "\t// ablation (ab-strings) end\n"),
            ((STRINGS_INCLUDE_ANCHOR, "#include <string>  // ablation (ab-strings)\n" "#include <string_view>\n"),)),
)

PREAMBLE = """\
// An ablation copy of design/review-runs/ablations.md, the header of the rbench arm {arm}:
// RegexMatcher v2's route headers at d1d73e99b (include/matcher/route/config.hpp, detail/words.hpp,
// pattern.hpp, table.hpp, lookup.hpp and runtime_table.hpp, in that order) copied under the namespace
// matcher::route_{tag} and the macro prefix MATCHER_ROUTE_{TAG}_, so that it links beside the pinned
// headers in one binary. Generated by tools/make_ablation.py, which also checks it against the pinned
// headers (--check).
//
{change}
#pragma once
"""


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def rename(text: str, tag: str) -> str:
    text = text.replace("namespace matcher::route\n", f"namespace matcher::route_{tag}\n")
    text = text.replace("}  // namespace matcher::route\n", f"}}  // namespace matcher::route_{tag}\n")
    return text.replace("MATCHER_ROUTE_", f"MATCHER_ROUTE_{tag.upper()}_")


def body(root: Path) -> str:
    """The six headers, includes gathered, in v2's own names (renamed per variant afterwards)."""
    base = root / "include" / "matcher" / "route"
    includes: list[str] = []
    bodies: list[str] = []
    for name in HEADERS:
        lines = []
        for line in read(base / name).split("\n"):
            m = INCLUDE.match(line)
            if line.strip() == "#pragma once":
                continue
            if m:
                if not m.group(1).startswith("<matcher/") and line not in includes:
                    includes.append(line)
                continue
            lines.append(line)
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines).strip("\n"))
        if "namespace matcher::route\n" not in text + "\n":
            raise SystemExit(f"make_ablation: {name} has no namespace matcher::route")
        bodies.append(text + "\n")
    return "\n".join(sorted(includes)) + "\n\n" + "\n".join(bodies)


def generate(root: Path, v: Variant) -> str:
    text = body(root)
    if v.anchor:
        found = text.count(v.anchor)
        if found != 1:
            raise SystemExit(f"make_ablation: {v.arm}: the anchor {v.anchor.strip()[:60]!r} occurs {found} times, not 1")
        if any(MARK not in line for line in v.change.rstrip("\n").split("\n")):
            raise SystemExit(f"make_ablation: {v.arm}: a line of the change is not marked")
        text = text.replace(v.anchor, v.change)
    for anchor, change in v.extra:
        found = text.count(anchor)
        if found != 1:
            raise SystemExit(f"make_ablation: {v.arm}: the anchor {anchor.strip()[:60]!r} occurs {found} times, not 1")
        if any(MARK not in line for line in change.rstrip("\n").split("\n") if line != anchor.rstrip("\n")):
            raise SystemExit(f"make_ablation: {v.arm}: a line of an extra change is not marked")
        text = text.replace(anchor, change)
    marked = (" Every line of it is marked \"ablation ({})\".".format(v.arm.removeprefix("regexmatcher-v2-"))
              if v.anchor else "")
    change = "\n".join("// " + line for line in
                       textwrap.wrap(f"The change from the renamed copy: {v.what}.{marked}", width=101))
    head = PREAMBLE.format(arm=v.arm, tag=v.tag, TAG=v.tag.upper(), change=change)
    return head + "\n" + rename(text, v.tag)


def one_change(copy: str, variant: str, v: Variant) -> list[str]:
    """Problems with the variant against the copy (empty: one hunk, every added line marked)."""
    back = variant.replace(f"matcher::route_{v.tag}", "matcher::route_copy")
    back = back.replace(f"MATCHER_ROUTE_{v.tag.upper()}_", "MATCHER_ROUTE_COPY_")
    head_end = "#pragma once\n"
    a = copy[copy.index(head_end):].split("\n")
    b = back[back.index(head_end):].split("\n")
    ops = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]
    problems = []
    hunks = 1 + len(v.extra)
    if v.anchor and len(ops) != hunks:
        problems.append(f"{v.arm}: {len(ops)} changed hunks, not {hunks}")
    if not v.anchor and ops:
        problems.append(f"{v.arm}: the copy differs from itself")
    for _, _, _, j1, j2 in ops:
        problems += [f"{v.arm}: unmarked line {line!r}" for line in b[j1:j2] if MARK not in line]
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regexmatcher", type=Path, required=True, help="RegexMatcher at the pinned commit")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--check", action="store_true", help="compare with the files on disk; write nothing")
    args = ap.parse_args()
    texts = {v.tag: generate(args.regexmatcher, v) for v in VARIANTS}
    problems = [p for v in VARIANTS for p in one_change(texts["copy"], texts[v.tag], v)]
    for p in problems:
        print(f"make_ablation: {p}")
    if problems:
        return 1
    bad = 0
    for v in VARIANTS:
        path = args.out_dir / f"route_{v.tag}.hpp"
        if args.check:
            same = path.exists() and read(path) == texts[v.tag]
            bad += 0 if same else 1
            print(f"make_ablation: {path.name} {'is' if same else 'is NOT'} the pinned headers renamed"
                  f"{' and its one change' if v.anchor else ''}")
        else:
            path.write_bytes(texts[v.tag].encode("utf-8"))
            print(f"make_ablation: wrote {path}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
