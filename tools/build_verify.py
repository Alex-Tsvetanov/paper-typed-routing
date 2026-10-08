#!/usr/bin/env python3
"""Link tools/verify_answers.cpp from an rbench build's own objects.

    build_verify.py RBENCH_BUILD_DIR OUT_DIR

Compiles verify_answers.cpp with the flags the build compiled bench/main.cpp with (its entry
in compile_commands.json), then runs the build's own link command for rbench (ninja -t
commands) with main.cpp's object replaced by verify_answers.o and the output renamed: every
arm's object, bench/core's objects and every library are those of the build, unchanged.
Writes OUT_DIR/verify_answers and OUT_DIR/build_verify.json (the commands run, and the
sha256 of the build's rbench and of the new binary).
"""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    build, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    src = Path(__file__).resolve().parent / "verify_answers.cpp"
    entries = json.loads((build / "compile_commands.json").read_text())
    main_entry = [e for e in entries if e["file"].endswith("/bench/main.cpp") or e["file"].endswith("bench/main.cpp")]
    if len(main_entry) != 1:
        sys.exit("build_verify: main.cpp is not in compile_commands.json exactly once")
    e = main_entry[0]
    args = e.get("arguments") or shlex.split(e["command"])
    obj = out / "verify_answers.o"
    compile_args = []
    skip = False
    for i, x in enumerate(args):
        if skip:
            skip = False
            continue
        if x == "-o":
            compile_args += ["-o", str(obj)]
            skip = True
        elif x == "-c":
            compile_args += ["-c"]
        elif x.endswith("main.cpp") and Path(x).name == "main.cpp":
            compile_args += [str(src)]
        else:
            compile_args.append(x)
    subprocess.run(compile_args, cwd=e["directory"], check=True)
    link = subprocess.run(["ninja", "-C", str(build), "-t", "commands", "rbench"], capture_output=True, text=True,
                          check=True).stdout.strip().splitlines()[-1]
    main_obj = "CMakeFiles/rbench.dir/main.cpp.o"
    if link.count(main_obj) != 1 or " -o rbench " not in link:
        sys.exit("build_verify: the link command does not have the expected shape")
    new_link = link.replace(main_obj, str(obj)).replace(" -o rbench ", f" -o {out / 'verify_answers'} ")
    subprocess.run(new_link, shell=True, cwd=build, check=True)
    info = {"build": str(build), "rbench_sha256": sha256(build / "rbench"), "compile": compile_args,
            "link": new_link, "verify_answers_sha256": sha256(out / "verify_answers")}
    (out / "build_verify.json").write_text(json.dumps(info, indent=1) + "\n")
    print(json.dumps({"verify_answers": str(out / "verify_answers"), "rbench_sha256": info["rbench_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
