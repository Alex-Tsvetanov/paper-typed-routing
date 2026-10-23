#!/usr/bin/env bash
# bringup.sh OUT_DIR: round 3's bring-up on the laptop's Arch (STATE.md, Laptop requests 0, 2 and 3):
# the Release builds of the three programs, the request sets, the functional suite, the runner's
# tests and one pass of the runner in count mode. Untimed: nothing here reads a time, a rate or a
# latency of any program; count mode reads none.
#
# Steps, in order; the first that fails stops the job (exit 1), and OUT_DIR/steps.txt says which:
#   toolchains  clang, Go and Rust must be the pinned ones (EXPECT_CLANG 22.1.8, EXPECT_GO go1.27.3,
#               EXPECT_RUST 1.99.0); every version goes to OUT_DIR/versions.txt;
#   build       the paper's root project, clang, Release, all targets, in P2R3/build-<commit, 9
#               characters> (a fresh folder: the job stops if it exists);
#   ctest       its whole CTest suite;
#   inputs      what each target compiled (lab/bin/inputs_hash.py, as t3/sanitize.sh hashes it), for
#               D5's gate to match with the records;
#   programs    the Go and Rust programs against that build's v2 library (t3/build_programs.py) in
#               P2R3/progs-<commit>;
#   sets        the request sets in P2R3/sets: made by that build's e2e_requests unless they exist,
#               then every cell checked against t3/requests-manifest.tsv, all 160 of them;
#   suite       t3/run_checks.py over the three programs, every arm (STATE.md, Functional checks);
#   runner      t3/test_p2run.py, the runner's tests;
#   count       t3/p2run.py in count mode over every arm of the three programs, both shapes, m = 10
#               and 1,000, the pair (111, 211), 20,000 requests a window, pinned as the campaign is.
# OUT_DIR gets the logs and JSON (build-info.json, build.inputs.json, suite.jsonl, count.jsonl);
# the build trees stay in P2R3, outside the job's folder.
#
# Environment (defaults for the laptop): P2R3 (~/lab/p2r3); INPUTS_HASH_PY ($LAB_TOOLS/../bin/
# inputs_hash.py, the deployed Papers repo's); P2_GO (~/opt/p2/go1.27.3/bin); RUSTUP_HOME
# (~/opt/rustup), CARGO_HOME (~/opt/cargo), RUSTUP_TOOLCHAIN (1.99.0); JOBS (nproc); P2_CPU_SERVER,
# P2_CPU_GEN, P2_CPU_HOUSE (14, 2-13, 0-1). Downloads as t3/sanitize.sh's: FetchContent archives
# checked against their sha256 pins, Go modules against go.sum (GOPROXY=direct, GOTOOLCHAIN=local),
# crates against Cargo.lock (--locked).
set -uo pipefail
export GOPROXY=direct GOTOOLCHAIN=local

out=${1:?usage: bringup.sh OUT_DIR}
mkdir -p "$out"
out=$(cd "$out" && pwd)
here=$(cd "$(dirname "$0")/.." && pwd)
root=$(cd "$here/.." && pwd)
p2r3=${P2R3:-$HOME/lab/p2r3}
ih=${INPUTS_HASH_PY:-${LAB_TOOLS:+$LAB_TOOLS/../bin/inputs_hash.py}}
export RUSTUP_HOME=${RUSTUP_HOME:-$HOME/opt/rustup} CARGO_HOME=${CARGO_HOME:-$HOME/opt/cargo}
export RUSTUP_TOOLCHAIN=${RUSTUP_TOOLCHAIN:-1.99.0}
export PATH=${P2_GO:-$HOME/opt/p2/go1.27.3/bin}:$CARGO_HOME/bin:$PATH
jobs=${JOBS:-$(nproc)}
exec > >(tee -a "$out/bringup.log") 2>&1

fail() { echo "$1 1 $2" >> "$out/steps.txt"; echo "STOPPED at $1: $2"; exit 1; }
ok() { echo "$1 0 ${2:-}" >> "$out/steps.txt"; echo "== $1 done ${2:-}"; }

echo "bringup start, paper $(git -C "$root" rev-parse HEAD), host $(uname -n) $(uname -r)"
[ -n "$ih" ] && [ -f "$ih" ] || fail toolchains "no inputs_hash.py (INPUTS_HASH_PY or LAB_TOOLS)"
[ -z "$(git -C "$root" status --porcelain)" ] || fail toolchains "the paper clone has local changes"
{
    echo "clang: $(clang++ --version | head -1)"
    echo "go: $(go version)"
    echo "rustc: $(rustc --version)"
    echo "cargo: $(cargo --version)"
    echo "cmake: $(cmake --version | head -1)"
    echo "ninja: $(ninja --version)"
    echo "python: $(python3 --version)"
} > "$out/versions.txt" 2>&1
cat "$out/versions.txt"
grep -q "clang version ${EXPECT_CLANG:-22.1.8}" "$out/versions.txt" || fail toolchains "clang is not ${EXPECT_CLANG:-22.1.8}"
grep -q "go version ${EXPECT_GO:-go1.27.3} " "$out/versions.txt" || fail toolchains "go is not ${EXPECT_GO:-go1.27.3}"
grep -q "rustc: rustc ${EXPECT_RUST:-1.99.0} " "$out/versions.txt" || fail toolchains "rustc is not ${EXPECT_RUST:-1.99.0}"
ok toolchains

head9=$(git -C "$root" rev-parse --short=9 HEAD)
build=$p2r3/build-$head9
progs=$p2r3/progs-$head9
[ ! -e "$build" ] && [ ! -e "$progs" ] || fail build "$build or $progs exists; a bring-up build is never made again over one"
mkdir -p "$p2r3"
cmake -S "$root" -B "$build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
    "-DP2GEN_COMMIT=$(git -C "$root" rev-parse HEAD)" > "$out/build.log" 2>&1 &&
    cmake --build "$build" -j"$jobs" >> "$out/build.log" 2>&1 || fail build "see build.log"
ok build "$(sed -n 's/^-- mserver: external arms //p' "$out/build.log" | head -1)"

(cd "$build" && ctest --output-on-failure > "$out/ctest.log" 2>&1) || fail ctest "see ctest.log"
ok ctest "$(grep -Eo '[0-9]+% tests passed.*' "$out/ctest.log" | tail -1)"

mserver=$build/server/mserver
arms=$("$mserver" --router '?' 2>&1 | sed -n 's/^router arms://p')
"$mserver" --router '??' > "$out/router-releases.txt" 2>&1
n=$(INPUTS_HASH_PY=$ih bash "$here/inputs.sh" "$build" "$out/build" 2> "$out/inputs.err") || fail inputs "see inputs.err"
ok inputs "$n targets"

python3 "$here/build_programs.py" --cxx-build "$build" --out "$progs" -j "$jobs" > "$out/programs.log" 2>&1 ||
    fail programs "see programs.log"
cp "$progs/build-info.json" "$out/build-info.json"
go_bin=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["go"]["binary"])' "$progs/build-info.json")
rust_bin=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["rust"]["binary"])' "$progs/build-info.json")
ok programs

sets=$p2r3/sets
if [ ! -e "$sets/manifest.tsv" ]; then
    python3 "$here/make_requests.py" --bin "$build/e2e_requests" --out "$sets" > "$out/sets.log" 2>&1 ||
        fail sets "make_requests.py failed; see sets.log"
fi
python3 "$here/make_requests.py" --verify "$sets" --manifest "$here/requests-manifest.tsv" --complete >> "$out/sets.log" 2>&1 ||
    fail sets "the request sets differ from the manifest; see sets.log"
ok sets "$(tail -1 "$out/sets.log")"

python3 "$here/run_checks.py" --data "$sets" --mserver "$mserver" --go "$go_bin" --rust "$rust_bin" \
    --out "$out/suite.jsonl" > "$out/suite.out" 2>&1 || fail suite "$(tail -1 "$out/suite.out")"
ok suite "$(tail -1 "$out/suite.out")"

python3 "$here/test_p2run.py" > "$out/runner-tests.log" 2>&1 || fail runner "see runner-tests.log"
ok runner "$(tail -1 "$out/runner-tests.log")"

marms=$(python3 -c 'import json,sys; print(json.dumps([a for a in sys.argv[1].split() if a != "v1"]))' "$arms")
python3 - "$out/count-plan.json" "$build/t3/gen/p2gen" "$sets" "$mserver" "$marms" "$go_bin" "$rust_bin" \
    "${P2_CPU_SERVER:-14}" "${P2_CPU_GEN:-2-13}" "${P2_CPU_HOUSE:-0-1}" <<'EOF'
import json, sys
out, p2gen, sets, mserver, marms, go, rust, server, gen, house = sys.argv[1:11]
plan = {"_comment": "t3/jobs/bringup.sh's count step: count mode, untimed", "p2gen": p2gen, "data_root": sets,
        "shapes": ["mixed-disjoint", "static"], "sizes": [10, 1000], "pairs": [[111, 211]],
        "cpus": {"server": int(server), "generator": gen}, "housekeeping_cpus": house, "connections": 64,
        "ready_timeout_s": 120, "verify_sets": True,
        "programs": [{"name": "mserver", "path": mserver, "arms": json.loads(marms)},
                     {"name": "mserver-go", "path": go, "arms": ["v2", "httprouter", "gin", "nethttp", "chi", "null"]},
                     {"name": "mserver-rs", "path": rust, "arms": ["v2", "matchit", "path-tree", "actix-router", "null"]}]}
json.dump(plan, open(out, "w", encoding="utf-8"), indent=1)
EOF
python3 "$here/p2run.py" "$out/count-plan.json" --out "$out/count.jsonl" --count 20000 --workdir "$p2r3/count-$head9.work" \
    > "$out/count.out" 2>&1 || fail count "$(tail -1 "$out/count.out")"
ok count "$(tail -1 "$out/count.out")"
echo "bringup done, build $build, programs $progs, sets $sets"
