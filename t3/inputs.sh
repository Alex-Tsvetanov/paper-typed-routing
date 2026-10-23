#!/usr/bin/env bash
# inputs.sh BUILD OUT_PREFIX: what each measured C++ target of a round-3 build compiled, for D5's
# records and gate: lab/bin/inputs_hash.py (INPUTS_HASH_PY) in project mode over mserver and the
# libraries it links (mserver_arms, mserver_http1, mserver_loop, mserver_external, mserver_v1 where
# built, one arm_<name> per external arm, since a target's hash covers its own translation units
# only), v2's C interface (p2v2_c, p2v2), p2gen with p2gen_core and p2gen_net, and e2e_requests;
# RegexMatcher v2 is the dependency root "regexmatcher". Writes OUT_PREFIX.inputs.json, and
# OUT_PREFIX.v2-include.json with the hash of mserver_arms's and p2v2_c's inputs under
# regexmatcher/include/. Prints the number of targets. Used by t3/sanitize.sh and t3/jobs/bringup.sh.
set -uo pipefail
build=${1:?usage: inputs.sh BUILD OUT_PREFIX}
prefix=${2:?usage: inputs.sh BUILD OUT_PREFIX}
ih=${INPUTS_HASH_PY:-}
[ -n "$ih" ] && [ -f "$ih" ] || { echo "inputs.sh: INPUTS_HASH_PY names no file" >&2; exit 2; }
arms=$("$build/server/mserver" --router '?' 2>&1 | sed -n 's/^router arms://p')
[ -n "$arms" ] || { echo "inputs.sh: $build/server/mserver lists no arm" >&2; exit 2; }
targets=(mserver mserver_arms mserver_http1 mserver_loop mserver_external p2v2_c p2v2 p2gen p2gen_core p2gen_net e2e_requests)
[[ " $arms " == *" v1 "* ]] && targets+=(mserver_v1)
for a in $arms; do
    case $a in v2 | v1 | null) ;; *) targets+=("arm_${a//-/_}") ;; esac
done
targs=()
for t in "${targets[@]}"; do targs+=(--target "$t"); done
common=(--root-label project --config-key CMAKE_BUILD_TYPE --dep-root regexmatcher=RegexMatcher_SOURCE_DIR)
python3 "$ih" --build "p2r3=$build" "${targs[@]}" "${common[@]}" --out "$prefix.inputs.json" > /dev/null || exit 1
python3 "$ih" --build "p2r3=$build" --target mserver_arms --target p2v2_c "${common[@]}" \
    --label-hash regexmatcher/include/ --out "$prefix.v2-include.json" > /dev/null || exit 1
echo "${#targets[@]}"
