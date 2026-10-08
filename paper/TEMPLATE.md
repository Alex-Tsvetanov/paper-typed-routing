# The MDPI LaTeX template of this paper

## Source

- Downloaded by Alex from mdpi.com on 2026-09-28 (the site refuses scripted downloads, so no
  agent downloaded it).
- File: `MDPI_template_ACS.zip`, 671,712 bytes, sha256
  `62744425fbcec9cd3e58147cbee65bdec2e2ff0440f29792c26edc97a11b6c70`, checked again before use.
- Contents: `Definitions/` (the files below), `template.tex` and `template.pdf`. Nothing
  executable. `template.tex` and `template.pdf` are not copied here.
- Class version: `mdpi.cls` declares `\mdpidate` 2026-09-11 and `\mdpiversion` v6.5a.

## Files copied into `paper/Definitions/`

| file | bytes | sha256 |
|---|---:|---|
| journalnames.tex | 143,363 | c8c035b1980b852336584428b44499fdd1dc069c7be8985f258f2ef282775233 |
| logo-mdpi.eps | 563,678 | f02d31469c6b2666c9de2da8d8731773bce3751d2fa99a27ff4bcf61a106cdcf |
| logo-orcid.pdf | 12,671 | 0558a0097dc4d1ffe3f4a1b3c9b4b98c6e568eac7d7439d447ca56ed1a8ec759 |
| logo-updates.eps | 287,998 | 71ad8b00bcca718b62f3286af02ea56678e8199b5843d7ed4fdc86bd969c2809 |
| mdpi.bst | 23,683 | 3b747eee144173c46a43562ead905c26322c7cb394e350a925d36dcf63884680 |
| mdpi.cls | 61,807 | 658dbb5b2db2f6560bf3de3ecff7efac310a5817721eebd7539c1990b5345f01 |
| mdpi_apacite.bst | 138,426 | c7fffe0231922e5521dc360889fafe941ee26d154c1ce4e167e4ec9f2d13498f |
| mdpi_apacite.sty | 71,377 | a77a994f978c1860ff14dbcae74631f3ed835b418adbdcf84de2f06d98c34599 |
| mdpi_chicago.bst | 37,920 | 4a73faf6e0cf1a225d1b9a41a6955d3cc29a55c5fdce662177d00eee3946ce36 |
| unicode.tex | 7,487 | 1a41f6c85db06401a4582008e6b8933c7212d17541497701797a55fe473d19e0 |

The files are unchanged, with one exception in line endings. `journalnames.tex` comes with
CRLF line endings, and the repository stores every text file with LF (`.gitattributes`,
`* text=auto eol=lf`), so its committed bytes hash to `8a350ffc378f02d3c0ce1264c16a65caaeb7c3cd34ea9845fee7df9a5a6765c8`; only the line
endings differ from the zip's file. The other files are byte for byte as in the zip. The paper uses `\documentclass[futureinternet,article,submit,oneauthor]`,
and the class selects the numbered style `mdpi.bst` itself for Future Internet; the Chicago and
APA variants are not used.

## Licence terms found in the files

- `mdpi.cls`, `mdpi.bst`, `journalnames.tex`, `unicode.tex`: no licence statement. `mdpi.cls`
  names its authors and a contact (latex@mdpi.com). Its only licence text is the Creative
  Commons notice it prints on published articles (CC BY 4.0, or CC BY-NC-ND 4.0 for some
  journals), which is the licence of an article, not of the class.
- `mdpi_apacite.sty` and `mdpi_apacite.bst`: "Copyright (C) 1994-2013 Erik Meijer and any
  individual authors listed elsewhere in this file", part of the apacite package, with no
  licence text in the files.
- `mdpi_chicago.bst`: a header naming Glenn Paulley as author (version 4, 1992), no licence text.
- The logos carry no licence text.

No file grants or restricts redistribution explicitly. MDPI distributes the template for authors
to use in submissions. Alex decides whether the template files stay in a public repository.

## Page ranges without a range dash

`mdpi.bst`'s `n.dashify` turns every `-` of a `pages` field into `--`, and `multi.page.check`
decides between "p." and "pp." by looking for `-`, `,` or `+`. `refs.bib` therefore writes a page
range as `1\bibhyph{,}4`, and `main.tex` defines `\newcommand{\bibhyph}[1]{-}`. BibTeX sees a
comma, so it prints "pp."; LaTeX drops the comma and prints a hyphen. `mdpi.bst` is not edited.
