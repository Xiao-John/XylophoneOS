#!/bin/sh
# Optional: rebuild the vendored newlib prefix. Not run by make build.
set -eu
VERSION=4.6.0.20260123
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CACHE=${CACHE:-/tmp}
SRC="$CACHE/newlib-$VERSION"
BUILD="$CACHE/newlib-$VERSION-build"
PREFIX="$CACHE/newlib-$VERSION-prefix"
if [ ! -d "$SRC" ]; then
    mkdir -p "$SRC"
    curl -L --http1.1 -C - "https://sourceware.org/pub/newlib/newlib-$VERSION.tar.gz" -o "$CACHE/newlib.tar.gz"
    tar -xzf "$CACHE/newlib.tar.gz" -C "$SRC" --strip-components=1
fi
rm -rf "$BUILD" "$PREFIX"
mkdir "$BUILD"
cd "$BUILD"
"$SRC/configure" --target=x86_64-elf --prefix="$PREFIX" --disable-multilib \
    --disable-newlib-supplied-syscalls --disable-libgloss \
    --disable-newlib-io-long-double --disable-newlib-io-long-long \
    --disable-newlib-io-c99-formats --disable-newlib-io-pos-args
make -j4
make install
echo "Copy $PREFIX/x86_64-elf/{include,lib/libc.a,lib/libm.a} into $ROOT/src/third_party/newlib/x86_64-elf/"
