#!/bin/sh
# One t1gen self-test case against a fresh t1null. Usage: selftest.sh CASE T1GEN T1NULL
# Passes only if the case's expectations hold and both processes exit cleanly, which
# under a sanitizer build means neither reported anything.
set -u
case_name=$1; gen=$2; null=$3
dir=$(mktemp -d "${TMPDIR:-/tmp}/t1self.XXXXXX")
null_args="--port 0 --threads 2"
[ "$case_name" = dropped-pipeline ] && null_args="$null_args --drop-pipelined"
"$null" $null_args > "$dir/null.log" 2>&1 &
npid=$!
port=""
i=0
while [ $i -lt 100 ]; do
  port=$(sed -n 's/^t1null listening on port \([0-9][0-9]*\).*/\1/p' "$dir/null.log")
  [ -n "$port" ] && break
  i=$((i + 1)); sleep 0.1
done
if [ -z "$port" ]; then echo "t1null did not start"; cat "$dir/null.log"; kill "$npid"; exit 1; fi

common="--port $port --threads 2 --connections 8 --warmup 0.3 --duration 1.5 --out $dir/out.json"
# Three targets of different lengths, so pipelined requests of unequal size follow each
# other on one connection.
printf '/a\n/users/42/files/some-longer-name.txt\n\n/b/c\n' > "$dir/paths.txt"
printf '/ok\nno-slash\n' > "$dir/bad.txt"
case $case_name in
  closed-depth1)    "$gen" $common --depth 1 > "$dir/gen.log" 2>&1 ;;
  closed-depth16)   "$gen" $common --depth 16 > "$dir/gen.log" 2>&1 ;;
  open-loop)        "$gen" $common --rate 2000 > "$dir/gen.log" 2>&1 ;;
  dropped-pipeline) "$gen" $common --depth 16 --timeout-ms 200 > "$dir/gen.log" 2>&1 ;;
  paths-depth1)     "$gen" $common --depth 1 --paths "$dir/paths.txt" > "$dir/gen.log" 2>&1 ;;
  paths-depth16)    "$gen" $common --depth 16 --paths "$dir/paths.txt" > "$dir/gen.log" 2>&1 ;;
  paths-invalid)
    "$gen" $common --paths "$dir/bad.txt" > "$dir/gen.log" 2>&1
    grc=$?
    kill -TERM "$npid"; wait "$npid"
    cat "$dir/gen.log"
    ok=1
    [ $grc -eq 2 ] || ok=0
    grep -q "must start with '/'" "$dir/gen.log" || ok=0
    rm -rf "$dir"
    [ $ok -eq 1 ] && { echo "PASS $case_name"; exit 0; }
    echo "FAIL: want exit 2 and a message for a target without '/' (exit $grc)"; exit 1 ;;
  *) echo "unknown case $case_name"; kill "$npid"; exit 2 ;;
esac
grc=$?
kill -TERM "$npid"; wait "$npid"; nrc=$?
cat "$dir/gen.log" "$dir/null.log"
cat "$dir/out.json"
rc=0
[ $grc -eq 0 ] || { echo "FAIL: t1gen exit $grc"; rc=1; }
[ $nrc -eq 0 ] || { echo "FAIL: t1null exit $nrc"; rc=1; }
grep -q '^MEASURE_START ' "$dir/gen.log" && grep -q '^MEASURE_END ' "$dir/gen.log" || { echo "FAIL: markers"; rc=1; }
completed=$(sed -n 's/.*"measure":{"completed":\([0-9]*\).*/\1/p' "$dir/out.json")
errors=$(sed -n 's/.*"measure":{[^}]*"errors_total":\([0-9]*\).*/\1/p' "$dir/out.json")
timeouts=$(sed -n 's/.*"measure":{[^}]*"timeouts":\([0-9]*\).*/\1/p' "$dir/out.json")
[ -n "$completed" ] && [ "$completed" -gt 0 ] || { echo "FAIL: nothing completed"; rc=1; }
if [ "$case_name" = dropped-pipeline ]; then
  [ -n "$timeouts" ] && [ "$timeouts" -gt 0 ] || { echo "FAIL: dropped requests were not reported as timeouts"; rc=1; }
else
  [ "$errors" = 0 ] || { echo "FAIL: errors_total=$errors"; rc=1; }
fi
case $case_name in
  paths-*)
    grep -q '"paths":3,' "$dir/out.json" || { echo "FAIL: want three targets in the ring"; rc=1; } ;;
esac
if [ "$case_name" = open-loop ]; then
  # 2000/s for 1.5 s is 3000 slots; allow scheduling slack at the window edges.
  [ "$completed" -ge 2850 ] && [ "$completed" -le 3150 ] || { echo "FAIL: open loop completed $completed of ~3000"; rc=1; }
fi
rm -rf "$dir"
[ $rc -eq 0 ] && echo "PASS $case_name"
exit $rc
