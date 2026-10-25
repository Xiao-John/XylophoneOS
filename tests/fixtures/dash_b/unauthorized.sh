# SPDX-License-Identifier: Apache-2.0
CC=/usr/bin/x86_64-elf-gcc
"$CC" --sysroot=/sysroot -I/src -c /src/value.c -o /out/unauthorized.o
