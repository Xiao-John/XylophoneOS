#!/bin/bash
set -euo pipefail
source_root=/work/upstream
sdk_root=/work/sdk/sysroot
out=/work/unwind
mkdir "$out"
cd "$out"
CC=/work/tools/ccc CXX=/work/tools/cxx AR=x86_64-elf-ar RANLIB=x86_64-elf-ranlib \
    LD=x86_64-elf-ld NM=x86_64-elf-nm gcc_cv_target_thread_file=posix \
    "$source_root/libgcc/configure" --build="$("$source_root/config.guess")" \
    --host=x86_64-elf --disable-shared --disable-gcov
plugin=$(x86_64-elf-gcc -print-file-name=plugin)/include
printf '#define USED_FOR_TARGET 1\n' >tconfig.h
printf '/* 64-bit ELF selects no extra libgcc target header. */\n' >libgcc_tm.h
cp "$source_root/libgcc/unwind-generic.h" unwind.h
cp "$source_root/libgcc/config/no-unwind.h" md-unwind-support.h
cp "$source_root/libgcc/config/no-unwind.h" md-unwind-def.h
cp "$source_root/libgcc/gthr-posix.h" gthr-default.h
flags=(-B/work/tools/ -O2 -g0 -fexceptions -fbuilding-libgcc -fno-stack-protector -mno-red-zone
       -fno-pie -fno-pic -DIN_GCC -DIN_LIBGCC2 -DHAVE_CC_TLS -DHAVE_GAS_HIDDEN -DGTHREAD_USE_WEAK=0
       -nostdinc -I"$out" -I"$plugin" -I"$source_root/libgcc" -I"$source_root/include"
       -isystem "$sdk_root/usr/include" -isystem "$sdk_root/usr/lib/compiler-include")
for name in unwind-dw2 unwind-dw2-fde unwind-sjlj unwind-c emutls; do
    x86_64-elf-gcc "${flags[@]}" -MD -MF "$name.d" -c "$source_root/libgcc/$name.c" -o "$name.o"
done
x86_64-elf-nm -u "$out"/*.o
