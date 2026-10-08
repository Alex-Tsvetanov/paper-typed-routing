#!/usr/bin/env bash
# The validation of the dispatch-resource stall counters (bench/core/cache_counters.hpp) on L:
# a pointer chase over 128 MiB (mode 0, memory-bound) against a dependent multiply chain
# (mode 1, compute-bound), 50,000,000 steps each, with every unit-mask bit of events 0xae and
# 0xaf counted on its own, in groups of cycles and four events (the NMI watchdog holds one of
# the six counters). Run under lab/bin/lablock, pinned to CPU 2.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
cc -O2 -o "$here/chase" "$here/chase.c"
for mode in 0 1; do
    for ev in ae af; do
        for half in 0 1; do
            e="cycles"
            for k in 0 1 2 3; do
                bit=$((half * 4 + k))
                e="$e,cpu/event=0x$ev,umask=$(printf '0x%02x' $((1 << bit)))/"
            done
            echo "## mode $mode event 0x$ev bits $((half * 4))-$((half * 4 + 3))"
            taskset -c 2 perf stat -x, -e "{$e}" "$here/chase" 16777216 "$mode" 2>&1 >/dev/null
        done
    done
done
