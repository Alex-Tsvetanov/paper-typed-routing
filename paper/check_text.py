#!/usr/bin/env python3
"""Checks the paper's sources against the writing rules (Papers CLAUDE.md, D4 and the numbers rule).

    python paper/check_text.py

1. No en dash, em dash or other dash character, and no "--" or "---" (which LaTeX sets as
   dashes), in any .tex file of paper/ or in the generated macros of results/round2 (macros.tex
   and macros-paper.tex), comments included.
2. No digit in the prose of paper/*.tex: every number comes from those two files. Commands
   whose arguments are not prose (cite, ref, label, input, includegraphics, lengths, package
   options) are removed first, and a short list of names that contain digits is allowed (H1 to
   H7, C++20 and C++23, RFC numbers, HTTP/1.1, HTTP/2, 404 and 405, u64 and i64, L1d, L1 and L2, SHA-256,
   x86-64, T0 and T1, P0732, UTF-8, S1, GOAMD64, PCRE2, the postal address, 10^ in math, the arm names v1, v2
   and r3, macro parameters, and file names in texttt).
3. No sentence of more than 30 words, in the prose and the captions of paper/*.tex. A macro
   counts as one word, and a sentence may open with an arm or a router named in lower case.
   Tables, figures, listings, TODO and Pending blocks, and MDPI's fixed forms (author
   contributions, conflicts of interest) are left out.
4. Reported, not failed: sentences with two or more passive verbs.
Prints every problem and exits 1 if a check of 1 to 3 fails.
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"
ALLOWED = [r"\bH[1-7]\b", r"C\+\+2[03]", r"C\+\+", r"RFC~?\d+", r"HTTP/1\.1", r"HTTP/2", r"\b40[45]\b", r"\b[ui]64\b",
           r"\bL1d\b", r"\bL[12]\b", r"SHA-256", r"x86-64", r"\bT[01]\b", r"P0732", r"UTF-8",
           r"Bradistilov 11", r"10\^", r"\bS1\b", r"GOAMD64", r"\bPCRE2\b", r"\bRFC\b", r"\bv[12]\b", r"\br3\b", r"#\d",
           r"-j1", r"Sections? \d+(\.\d+)+( and \d+(\.\d+)+)?", r"\\newcommand\{\\orcidauthorA\}\{[^}]*\}", r"![0-9]+!", r"\\texttt\{[^}]*(/|\\_|\.py|\.sh|\.jsonl)[^}]*\}"]
STRIP = [r"\\vspace\{[^}]*\}", r"\\begin\{adjustwidth\}\{[^}]*\}\{[^}]*\}",
         r"\\cmidrule\([lr]*\)\{[^}]*\}", r"\\multicolumn\{\d+\}",
         r"\\(cite|ref|label|input|includegraphics|bibliography|bibliographystyle|url|href|setlength|"
         r"usepackage|documentclass|addlinespace|mac|usetikzlibrary)(\[[^\]]*\])?\{[^}]*\}(\{[^}]*\})?",
         r"\\begin\{tabular\}\{[^}]*\}", r"\\begin\{tabularx\}\{[^}]*\}\{[^}]*\}",
         r"\\(begin|end)\{[a-z*]+\}(\[[^\]]*\])?", r"\\[A-Za-z]+\*?", r"\[[0-9a-z=,.!]+\]"]
MAX_WORDS = 30
PASSIVE = re.compile(r"\b(is|are|was|were|be|been|being)\s+(\w+ly\s+)?(\w+ed|built|made|run|shown|given|found|"
                     r"kept|taken|done|seen|known|written|drawn|held|set|read|put|chosen|left)\b")


def uncomment(line: str) -> str:
    return re.split(r"(?<!\\)%", line, maxsplit=1)[0]


def check_dashes(path: Path) -> list[str]:
    bad = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if any(c in line for c in DASHES) or "--" in line:
            bad.append(f"{path.name}:{n}: dash: {line.strip()}")
    return bad


def body_lines(path: Path) -> list[tuple[int, str]]:
    """The lines to check for digits: in main.tex from \\begin{document}, elsewhere all; the
    body of a listing and of a tikzpicture is code, not prose, and is left out."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("\\Title{")), 0) if path.name == "main.tex" else 0
    out, skip = [], False
    for n, line in enumerate(lines[start:], start + 1):
        if re.search(r"\\begin\{(lstlisting|tikzpicture)\}", line):
            skip = True
        if not skip:
            out.append((n, line))
        if re.search(r"\\end\{(lstlisting|tikzpicture)\}", line):
            skip = False
    return out


def check_digits(path: Path) -> list[str]:
    bad = []
    for n, line in body_lines(path):
        text = uncomment(line)
        for pat in ALLOWED:
            text = re.sub(pat, " ", text)
        for pat in STRIP:
            text = re.sub(pat, " ", text)
        if re.search(r"\d", text):
            bad.append(f"{path.name}:{n}: digit: {line.strip()}")
    return bad


def argument(text: str, start: int) -> tuple[str, int]:
    """The brace group that opens at text[start] ('{'), and the index after it."""
    depth, i = 0, start
    while i < len(text):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[start + 1:i], i + 1
        i += 1
    return text[start + 1:], len(text)


def drop_command(text: str, name: str) -> str:
    out, i = [], 0
    while True:
        j = text.find("\\" + name + "{", i)
        if j < 0:
            return "".join(out) + text[i:]
        _, k = argument(text, j + len(name) + 1)
        out.append(text[i:j] + " ")
        i = k


def prose(path: Path) -> str:
    text = "\n".join(uncomment(l) for l in path.read_text(encoding="utf-8").splitlines())
    if path.name == "main.tex":
        text = text[text.find("\\abstract{"):]
    captions = []
    for env in ("table", "figure", "lstlisting", "tikzpicture"):
        pat = r"\\begin\{" + env + r"\}.*?\\end\{" + env + r"\}"
        for m in re.finditer(pat, text, flags=re.S):
            j = m.group(0).find("\\caption{")
            if j >= 0:
                captions.append(argument(m.group(0), j + len("\\caption"))[0])
        text = re.sub(pat, " ", text, flags=re.S)
    text = text + "\n\n" + "\n\n".join(captions)
    for name in ("TODO", "ForAlex", "Pending", "authorcontributions", "conflictsofinterest"):
        text = drop_command(text, name)
    text = re.sub(r"\\(cite|ref|label|input|bibliography|bibliographystyle)(\[[^\]]*\])?\{[^}]*\}", "", text)
    text = re.sub(r"\$[^$]*\$", " M ", text)
    text = re.sub(r"\\(texttt|emph|textbf|arm|shape|hex|mac)\{", "{", text)
    text = re.sub(r"\\(item|paragraph|runin|subsection|section)\*?", "\n\n", text)
    text = re.sub(r"\\VerifySwitch\{", "\n\n{", text)
    text = text.replace("}{", "}\n\n{")
    text = re.sub(r"\\[A-Za-z]+\*?", " X ", text)
    return text.replace("~", " ").replace("{", " ").replace("}", " ").replace("\\ ", " ")


# Names that are written in lower case and may open a sentence (the arms and the routers).
LOWER_NAMES = r"(?:v[12]|gin|glaze|matchit|r3|axum|chi|httprouter|actix-router|path-tree|cpp-httplib|regexmatcher)"


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.?!])\s+(?=[A-Z(]|X\b|``|" + LOWER_NAMES + r"(?!\w))|\n\s*\n", text)
    return [" ".join(p.split()) for p in parts if len(p.split()) > 1]


def check_sentences(path: Path) -> tuple[list[str], list[str]]:
    long, passive = [], []
    for s in sentences(prose(path)):
        n = len(s.split())
        if n > MAX_WORDS:
            long.append(f"{path.name}: {n} words: {s[:160]}")
        if len(PASSIVE.findall(s)) >= 2:
            passive.append(f"{path.name}: passive: {s[:160]}")
    return long, passive


def main() -> int:
    tex = sorted(HERE.glob("*.tex"))
    bad, notes = [], []
    for p in tex + [HERE.parent / "results/round2/macros.tex", HERE.parent / "results/round2/macros-paper.tex"]:
        bad += check_dashes(p)
    for p in tex:
        bad += check_digits(p)
        long, passive = check_sentences(p)
        bad += long
        notes += passive
    for b in bad:
        print(b)
    for n in notes:
        print("note", n)
    print(f"check_text: {len(tex)} files, {len(bad)} problems, {len(notes)} notes")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
