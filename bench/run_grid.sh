#!/usr/bin/env bash
# run_grid.sh RBENCH OUT_DIR: the agreement test, the probes and every cell of the grid, one
# process per cell and repetition, into OUT_DIR.
#
#   agree.jsonl   rbench agree over every arm, every shape, 10, 100 and 1000 routes, and every
#                 table seed of the publication design, judged by check_agree.py against the
#                 declared path semantics (semantics.json)
#   probes.jsonl  rbench probe per arm
#   cells.jsonl   rbench cell per (arm, shape, size, repetition) in plan.txt order; a cell that
#                 crashes or times out gets a line with status "crash" or "timeout", its exit
#                 code and its seeds
#   stderr.log    the processes' standard error (sanitizer reports land here)
#   verified.jsonl  the untimed check on every query of each process whose agreement pass
#                 stopped at its budget (tools/verify_unverified.py), with verify.txt, verify.err
#                 and verify/ (the check's binary, linked from this build)
#   env.txt, toolchain.txt, compile_commands.json, pin.json, plan.txt, exit.txt
#
# The publication design: REPS processes per cell (default 16), repetition k using the k-th
# (table seed, ring seed) pair of PAIRS, so that a cell's interval covers the variation over
# tables and rings as well as over processes. Every process is pinned to one CPU (CPU,
# default 2: physical core 1 of L, whose SMT sibling CPU 3 runs nothing of ours), the same
# for every arm.
#
# The scope of the slow reference arms is declared in the pre-specification and given here by
# SCOPE (arm:largest size:processes; default below): std-regex and regexmatcher-v1 run up to
# m = 10,000 in 3 processes per cell; every other arm, hash, radix and the ablation arm
# included, runs every cell in REPS processes.
#
# The stopping rule: when a cell's first process exceeds CELL_TIMEOUT, the cell's other
# processes are not run; each gets a line with status "skipped" and reason "exceeds budget".
#
# Environment: ARMS (default: every arm the binary lists), SCOPE, SHAPES (default the seven of the H1
# grid; github is exploratory and run by name), SIZES (default 10 100 1000 10000 100000),
# REPS (default 16; 1 with QUICK=1), PAIRS (default below), CPU, SEED (the shuffle of the
# cell order; default 20261009 (hypotheses-round2.md), none for the plan's order), CELL_TIMEOUT (seconds, default 1800), QUICK=1 (short cells,
# for sanitizer runs), MISS (permille of the ring's queries that match no route; default 0,
# the exploratory miss-heavy design uses 500), RING (ring size, default rbench's 4096), ZIPF
# (Zipf exponent of the ring, exploratory), VOCAB=long (12 to 24 letter literals, exploratory),
# NO_DECOY=1 (mixed-overlap without decoys, exploratory), RING_LAYOUT=queries (the timed loops
# read the queries instead of the compact copy, for the disclosure of that choice), PIN
# (pin.sh; default the Papers repo's lab/bin/pin.sh), ALLOW_UNPINNED=1, VERIFY=0 (skip the
# check on every query of the processes the agreement budget cut; see the end), VERIFY_JOBS.
set -euo pipefail

bin=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
out=${2:?usage: run_grid.sh RBENCH OUT_DIR}
here=$(cd "$(dirname "$0")" && pwd)
pin=${PIN:-$here/../../../lab/bin/pin.sh}
mkdir -p "$out"
out=$(cd "$out" && pwd)

arms=${ARMS:-$("$bin" list | grep -v '^#' | cut -f1 | tr '\n' ' ')}
arms=$(echo $arms | tr ' ' '\n' | awk '!seen[$0]++' | tr '\n' ' ')  # once each
scope=${SCOPE:-std-regex:10000:3 regexmatcher-v1:10000:3}
# The binary that runs an arm's cells (one binary holds every arm in round 2).
bin_of() { echo "$bin"; }
shapes=${SHAPES:-static param-last param-first rest wild mixed-disjoint mixed-overlap}
sizes=${SIZES:-10 100 1000 10000 100000}
timeout_s=${CELL_TIMEOUT:-1800}
if [ "${QUICK:-0}" = 1 ]; then reps=${REPS:-1}; else reps=${REPS:-16}; fi
# The round-2 publication pairs, held out (hypotheses-round2.md, section 4): table seeds 111 to
# 126 (rbench gen-ct compiles each) and ring seeds 211 to 226, the k-th pair (k = 1 to 16) being
# (110 + k, 210 + k): sixteen pairs that share no seed, so they are independent in the table and
# in the ring. Engineering and iteration runs use table seeds 1 to 5 and ring seeds 2 to 4
# (PAIRS). Round 1's seeds are not reused.
pairs=${PAIRS:-111:211 112:212 113:213 114:214 115:215 116:216 117:217 118:218 119:219 120:220 121:221 122:222 123:223 124:224 125:225 126:226}
order_seed=${SEED:-20261009}
cpu=${CPU:-2}
[ "$(echo $pairs | wc -w)" -ge "$reps" ] || { echo "run_grid: REPS=$reps but only $(echo $pairs | wc -w) PAIRS" >&2; exit 1; }

if [ -f "$pin" ]; then
    set +e
    bash "$pin" >"$out/pin.json"
    rc=$?
    set -e
    if [ "$rc" -ne 0 ] && [ "${ALLOW_UNPINNED:-0}" != 1 ]; then
        echo "run_grid: host is not pinned ($(cat "$out/pin.json")); set ALLOW_UNPINNED=1 to run anyway" >&2
        exit 1
    fi
elif [ "${ALLOW_UNPINNED:-0}" != 1 ]; then
    echo "run_grid: no pin.sh at $pin" >&2
    exit 1
fi

sibling=$(cat "/sys/devices/system/cpu/cpu$cpu/topology/thread_siblings_list" 2>/dev/null || echo na)
{
    echo "date: $(date -Is)"
    echo "binary: $bin"
    echo "binary_sha256: $(sha256sum "$bin" | cut -d' ' -f1)"
    echo "scope: $scope"
    echo "arms: $arms"
    echo "shapes: $shapes"
    echo "sizes: $sizes"
    echo "reps: $reps"
    echo "pairs (table_seed:ring_seed): $pairs"
    echo "seed: $order_seed"
    echo "cell_timeout_s: $timeout_s"
    echo "quick: ${QUICK:-0}"
    echo "miss_permille: ${MISS:-0}"
    echo "ring: ${RING:-default}"
    echo "zipf: ${ZIPF:-0}"
    echo "vocab: ${VOCAB:-default}"
    echo "decoys: $([ -n "${NO_DECOY:-}" ] && echo no || echo yes)"
    echo "ring_layout: ${RING_LAYOUT:-copy}"
    echo "cpu: $cpu (thread siblings: $sibling)"
    echo "uname: $(uname -a)"
    echo "cpu_model: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | sed 's/^ //')"
    echo "perf_event_paranoid: $(cat /proc/sys/kernel/perf_event_paranoid)"
    echo "nmi_watchdog: $(cat /proc/sys/kernel/nmi_watchdog 2>/dev/null || echo na)"
    echo "thp_enabled: $(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || echo na)"
    echo "thp_defrag: $(cat /sys/kernel/mm/transparent_hugepage/defrag 2>/dev/null || echo na)"
    echo "governor: $(sort -u /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | tr '\n' ' ')"
    echo "boost: $(cat /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || echo na)"
} >"$out/env.txt"

# The toolchains of every arm, and the flags their builds read from the environment.
{
    echo "cc: $(${CC:-clang} --version 2>/dev/null | head -1)"
    echo "cxx: $(${CXX:-clang++} --version 2>/dev/null | head -1)"
    echo "rustc: $(rustc -Vv 2>/dev/null | tr '\n' ' ')"
    echo "cargo: $(cargo -V 2>/dev/null)"
    echo "go: $(go version 2>/dev/null)"
    echo "go_env: $(go env GOAMD64 GOGC GOFLAGS CGO_CFLAGS 2>/dev/null | tr '\n' ' ')"
    echo "RUSTFLAGS: ${RUSTFLAGS-<unset>}"
    echo "GOAMD64: ${GOAMD64-<unset>}"
    echo "GOGC: ${GOGC-<unset>}"
    echo "GOFLAGS: ${GOFLAGS-<unset>}"
} >"$out/toolchain.txt"
[ -f "$(dirname "$bin")/compile_commands.json" ] && cp "$(dirname "$bin")/compile_commands.json" "$out/"

# The plan, in an order shuffled by SEED (SEED=none keeps the plan's order): arm, shape, size,
# repetition, table seed, ring seed.
python3 - "$order_seed" "$arms" "$shapes" "$sizes" "$reps" "$pairs" "$scope" >"$out/plan.txt" <<'EOF'
import random, sys
seed, arms, shapes, sizes = sys.argv[1], sys.argv[2].split(), sys.argv[3].split(), sys.argv[4].split()
seed = "" if seed == "none" else seed
reps, pairs = int(sys.argv[5]), [p.split(":") for p in sys.argv[6].split()]
scope = {a: (int(m), int(r)) for a, m, r in (x.split(":") for x in sys.argv[7].split())}
cells = [(a, s, m, k) for k in range(reps) for m in sizes for s in shapes for a in arms
         if int(m) <= scope.get(a, (10**12, reps))[0] and k < scope.get(a, (0, reps))[1]]
if seed:
    random.Random(int(seed)).shuffle(cells)
for a, s, m, k in cells:
    print(a, s, m, k, pairs[k][0], pairs[k][1])
EOF

status=0
: >"$out/stderr.log"
set +e
main_arms=$(echo $arms | tr ' ' '\n' | tr '\n' ',' | sed 's/,$//')
rbench_agree_rc=0
: >"$out/agree.jsonl"
if [ -n "$main_arms" ]; then
    "$bin" agree --arms "$main_arms" --shapes "$(echo $shapes | tr ' ' ',')" --sizes 10,100,1000 ${NO_DECOY:+--no-decoy} \
        >"$out/agree.jsonl" 2>>"$out/stderr.log"
    rbench_agree_rc=$?
fi
# rbench agree exits 1 on any disagreement; declared semantics (semantics.json) are not failures.
python3 "$here/check_agree.py" "$out/agree.jsonl" 2>>"$out/stderr.log"
agree_rc=$?
: >"$out/probes.jsonl"
probe_rc=0
for a in $arms; do
    "$(bin_of "$a")" probe --arm "$a" >>"$out/probes.jsonl" 2>>"$out/stderr.log" || probe_rc=$?
done
: >"$out/cells.jsonl"
failed=0
timed_out=0
over_budget=" "
seen=" "
while read -r a s m k ts rs; do
    echo "## cell $a $s $m rep $k seeds $ts $rs" >>"$out/stderr.log"
    case "$over_budget" in
        *" $a/$s/$m "*)
            printf '{"arm":"%s","shape":"%s","m":%s,"rep":%s,"table_seed":%s,"ring_seed":%s,"status":"skipped","reason":"exceeds budget"}\n' \
                "$a" "$s" "$m" "$k" "$ts" "$rs" >>"$out/cells.jsonl"
            continue ;;
    esac
    case "$seen" in *" $a/$s/$m "*) first=0 ;; *) first=1; seen="$seen$a/$s/$m " ;; esac
    line=$(timeout "$timeout_s" taskset -c "$cpu" "$(bin_of "$a")" cell --arm "$a" --shape "$s" --m "$m" \
        --seed "$ts" --ring-seed "$rs" ${QUICK:+--quick} ${MISS:+--miss "$MISS"} ${RING:+--ring "$RING"} \
        ${ZIPF:+--zipf "$ZIPF"} ${VOCAB:+--vocab "$VOCAB"} ${NO_DECOY:+--no-decoy} ${RING_LAYOUT:+--ring-layout "$RING_LAYOUT"} \
        2>>"$out/stderr.log")
    rc=$?
    if [ "$rc" -eq 0 ] && [ -n "$line" ]; then
        printf '%s\n' "$line" >>"$out/cells.jsonl"
    else
        kind=crash
        if [ "$rc" -eq 124 ]; then
            kind=timeout
            # The stopping rule: a cell whose first process ran out of budget runs no other.
            [ "$first" = 1 ] && over_budget="$over_budget$a/$s/$m "
        fi
        printf '{"arm":"%s","shape":"%s","m":%s,"rep":%s,"table_seed":%s,"ring_seed":%s,"status":"%s","exit":%s}\n' \
            "$a" "$s" "$m" "$k" "$ts" "$rs" "$kind" "$rc" >>"$out/cells.jsonl"
        # A timeout is an outcome the stopping rule reports ("exceeds budget"), not a failure.
        if [ "$kind" = timeout ]; then timed_out=$((timed_out + 1)); else failed=$((failed + 1)); fi
    fi
done <"$out/plan.txt"
# Every cell at every size judged against the declared semantics: an error, a crash or an
# undeclared disagreement fails the grid.
python3 "$here/check_agree.py" --cells "$out/cells.jsonl" 2>>"$out/stderr.log"
cells_rc=$?
# Every query of every process: a process whose agreement pass stopped at its 120 s budget
# (verified_all false) is checked again on every query of its ring, untimed, after the last
# measured cell, by tools/verify_answers linked from this binary's own build (tools/build_verify.py;
# every arm is in the one binary), VERIFY_JOBS at once (default every CPU: nothing is measured
# any more). verified.jsonl holds the checks; analysis/analyse.py reads it from the run
# directory, and analysis/cells.py fails a cell with a process that neither pass verified.
unverified=$(python3 -c 'import json, sys
print(sum(1 for l in open(sys.argv[1]) if l.startswith("{") for r in [json.loads(l)]
          if r.get("status") == "ok" and not r.get("null_arm") and r.get("verified_all") is False))' "$out/cells.jsonl")
verify_rc=0
if [ "${VERIFY:-1}" = 1 ] && [ "$unverified" -gt 0 ]; then
    tools=$(cd "$here/../tools" && pwd)
    echo "verify start $(date -Is): $unverified processes" >"$out/verify.txt"
    python3 "$tools/build_verify.py" "$(dirname "$bin")" "$out/verify" >>"$out/verify.txt" 2>&1 &&
        python3 "$tools/verify_unverified.py" "$out" --bin "$out/verify/verify_answers" --out "$out/verified.jsonl" \
            --jobs "${VERIFY_JOBS:-$(nproc)}" >>"$out/verify.txt" 2>"$out/verify.err"
    verify_rc=$?
    echo "verify end $(date -Is): exit $verify_rc" >>"$out/verify.txt"
fi
set -e
echo "agree_exit=$agree_rc rbench_agree_exit=$rbench_agree_rc probe_exit=$probe_rc failed_cells=$failed timed_out_cells=$timed_out cells_exit=$cells_rc unverified=$unverified verify_exit=$verify_rc" >"$out/exit.txt"
cat "$out/exit.txt"
[ "$agree_rc" -eq 0 ] && [ "$probe_rc" -eq 0 ] && [ "$failed" -eq 0 ] && [ "$cells_rc" -eq 0 ] && [ "$verify_rc" -eq 0 ] || status=1
exit $status
