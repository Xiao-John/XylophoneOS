#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Build Open Adventure inside XOS. Requires python3 (with xos/yaml.py) and the
# native GCC toolchain with /sysroot. No make, glob, or host-generated data.
set -e
SRC=/src/open-adventure
OUT=/out
CXX=/usr/bin/x86_64-elf-g++
CC=/usr/bin/x86_64-elf-gcc

python3 "$SRC/make_dungeon.py"

"$CXX" -std=c++17 -fno-exceptions -fno-rtti -D__xos__=1 -O2 \
    -isystem /sysroot/include -c "$SRC/xos_readline.cpp" -o "$OUT/xos_readline.o"

"$CC" -std=c99 -D_DEFAULT_SOURCE -D__xos__=1 -O2 \
    -I"$SRC/include" -isystem /sysroot/include -static --sysroot=/sysroot \
    -o "$OUT/advent" \
    "$SRC/main.c" "$SRC/init.c" "$SRC/actions.c" "$SRC/score.c" \
    "$SRC/misc.c" "$SRC/saveresume.c" "$SRC/dungeon.c" \
    "$OUT/xos_readline.o"
