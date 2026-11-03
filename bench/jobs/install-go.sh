#!/usr/bin/env bash
# install-go.sh [PREFIX]: the Go toolchain rbench's Go arms are pinned to (bench/cmake/pins.cmake,
# RB_NETHTTP_GO "go1.27.1-X:nodwarf5"), installed in user space on the laptop's Arch, for the review build
# (design/review-runs/README.md, "Toolchain trap") and its sanitizer records.
#
# The pinned string is what `go version` reports for Arch Linux's package go 2:1.27.1-1 (built with the
# experiment nodwarf5); the official go.dev archive of go1.27.1 reports plain "go1.27.1" and cannot pass
# the configure check of cmake/arm-nethttp.cmake. So the toolchain is that package, from the Arch Linux
# Archive:
#     https://archive.archlinux.org/packages/g/go/go-2:1.27.1-1-x86_64.pkg.tar.zst
#     sha256 265d4359ebe8efd0b6f66e71a6a971100dfa58072f849f5867588419a76c232d
# (the sha256 of the file fetched on the desktop on 2026-11-03, whose `go version` was read there as
# "go version go1.27.1-X:nodwarf5 linux/amd64"; the archive publishes a PGP signature, not a sha256).
#
# The script downloads the package into PREFIX's parent, checks its sha256 and refuses on any other,
# unpacks only the toolchain (usr/lib/go) into PREFIX (default ~/opt/p2/go1.27.1-nodwarf5), checks that
# PREFIX/bin/go reports the pinned version, and prints the go binary to give to the builds (GO=... for
# bench/jobs/review-grid.sh and bench/sanitize_rbench.sh, which put it first on PATH and pass -DRB_GO).
# It is idempotent: an install that already reports the pinned version, with the stamp of this archive,
# is left as it is. It never touches the system's Go (/usr/bin/go, /usr/lib/go), PATH or any profile, and
# needs no root. Downloads: the one archive above. Tools: curl, sha256sum, tar with zstd (Arch's base).
set -euo pipefail

URL="https://archive.archlinux.org/packages/g/go/go-2:1.27.1-1-x86_64.pkg.tar.zst"
SHA256=265d4359ebe8efd0b6f66e71a6a971100dfa58072f849f5867588419a76c232d
PINNED="go version go1.27.1-X:nodwarf5 linux/amd64"

prefix=${1:-$HOME/opt/p2/go1.27.1-nodwarf5}
case "$prefix" in
    /usr/* | /bin/* | /opt/go* | "") echo "install-go: refusing a system prefix '$prefix'" >&2; exit 2 ;;
esac
parent=$(dirname "$prefix")
stamp=$prefix/.install-go-sha256

report() {
    GOTOOLCHAIN=local "$prefix/bin/go" version 2>/dev/null || true
}

if [ -x "$prefix/bin/go" ] && [ "$(report)" = "$PINNED" ] && [ "$(cat "$stamp" 2>/dev/null)" = "$SHA256" ]; then
    echo "install-go: already installed: $prefix/bin/go ($PINNED)"
    echo "GO=$prefix/bin/go"
    exit 0
fi
if [ -e "$prefix" ]; then
    echo "install-go: $prefix exists but is not this toolchain ($(report)); move it away first" >&2
    exit 1
fi

mkdir -p "$parent"
pkg=$parent/go-2:1.27.1-1-x86_64.pkg.tar.zst
if [ ! -f "$pkg" ]; then
    curl -fsSL --retry 3 -o "$pkg.part" "$URL"
    mv "$pkg.part" "$pkg"
fi
got=$(sha256sum "$pkg" | cut -d' ' -f1)
if [ "$got" != "$SHA256" ]; then
    echo "install-go: sha256 of $pkg is $got, not $SHA256; refusing (the file is left for inspection)" >&2
    exit 1
fi

tmp=$(mktemp -d "$parent/.install-go.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
tar --zstd -xf "$pkg" -C "$tmp" usr/lib/go
mv "$tmp/usr/lib/go" "$prefix"
echo "$SHA256" >"$stamp"
if [ "$(report)" != "$PINNED" ]; then
    echo "install-go: $prefix/bin/go reports '$(report)', not '$PINNED'; removing the install" >&2
    rm -rf "$prefix"
    exit 1
fi
echo "install-go: installed $prefix/bin/go ($PINNED) from $URL (sha256 $SHA256)"
echo "GO=$prefix/bin/go"
