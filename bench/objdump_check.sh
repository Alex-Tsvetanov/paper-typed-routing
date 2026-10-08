#!/bin/bash
# objdump_check.sh CXX LABEL OLD_HEADER OLD_NS NEW_INCLUDE_DIR NEW_HEADER NEW_NS [FLAG...]
# The objdump check of design/round2/regexmatcher-v2.md, section 9: compiles find_v2, the
# out-of-line lookup both v2 arms of the harness call, once against the round-1 header
# (OLD_HEADER, namespace OLD_NS) and once against RegexMatcher v2 (NEW_HEADER under
# NEW_INCLUDE_DIR, namespace NEW_NS), at -O3 and the extra FLAGs; disassembles both; drops
# addresses and section names (which carry the mangled names); maps both namespaces to NS; and
# diffs. The script of lab/evidence/2026-09-30-W-regexmatcher-v2-objdump with the FLAGs added, so
# that the check runs at the flags the harness builds with (-march=native since the instruction
# set of hypotheses-round2.md, section 2).
set -u
cxx=$1; label=$2; old=$3; oldns=$4; inc=$5; hdr=$6; ns=$7
shift 7
W=$HOME/od/$label; mkdir -p "$W"
printf '#include "%s"\nnamespace R = %s;\n[[gnu::noinline]] R::Match find_v2(const R::TableView& view, unsigned method, std::string_view path) { return R::find(view, method, path); }\n' "$old" "$oldns" > "$W/a.cpp"
printf '#include <%s>\nnamespace R = %s;\n[[gnu::noinline]] R::Match find_v2(const R::TableView& view, unsigned method, std::string_view path) { return R::find(view, method, path); }\n' "$hdr" "$ns" > "$W/b.cpp"
flags=(-O3 -DNDEBUG -std=c++23 -fsized-deallocation "$@")
$cxx "${flags[@]}" -c "$W/a.cpp" -o "$W/a.o" && $cxx "${flags[@]}" "-I$inc" -c "$W/b.cpp" -o "$W/b.o" || exit 2
norm() { objdump -d --no-show-raw-insn -M intel -C "$1" | grep -v 'file format' | grep -v '^Disassembly of section' \
  | sed -E 's/^ +[0-9a-f]+:\s*//; s/^[0-9a-f]+ </</; s/\b[0-9a-f]+ <([^>]*)>/<\1>/g' | sed "s/$2/NS/g" | grep -v '^$'; }
norm "$W/a.o" "$oldns" > "$W/a.s"; norm "$W/b.o" "$ns" > "$W/b.s"
echo "$label ($($cxx --version | head -1); flags ${flags[*]}): functions $(grep -c '^<' "$W/a.s") and $(grep -c '^<' "$W/b.s"), lines $(wc -l < "$W/a.s") and $(wc -l < "$W/b.s"), sha256 $(sha256sum < "$W/a.s" | cut -c1-16) and $(sha256sum < "$W/b.s" | cut -c1-16)"
if diff -q "$W/a.s" "$W/b.s" > /dev/null; then echo "IDENTICAL"; else echo "DIFFERENT"; diff "$W/a.s" "$W/b.s" | head -40; fi
