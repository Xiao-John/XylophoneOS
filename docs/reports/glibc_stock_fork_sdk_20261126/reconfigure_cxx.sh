#!/bin/bash
set -euo pipefail
cd /work
source=/work/upstream
sdk=/work/sdk/sysroot
archive=/work/material/gcc-16.2.0.tar.xz
printf '%s  %s\n' e6738e29597f733270731aa90600f37ffdc045079dfc27ec7e8192cc81085c3e "$archive" | sha256sum -c -
grep -q '^\[GNUPG:\] VALIDSIG 7F74F97C103468EE5D750B583AB00996FC26A641 ' logs/gpgv.status
test -f "$sdk/usr/lib/libxos_terminal.a"
test -f "$source/libstdc++-v3/configure"
grep -q '\*-xos | \*-linux\* | \*-uclinux\*' "$source/libstdc++-v3/configure"
python3 - <<'PY'
from pathlib import Path
driver = Path('tools/driver')
source = driver.read_text()
old = '"$lib/libc.a" "$lib/libm.a" "$lib/libgcc.a"'
new = '"$lib/libc.a" "$lib/libm.a" "$lib/libxos_terminal.a" "$lib/libgcc.a"'
if source.count(old) != 1:
    raise RuntimeError('previous configure driver does not have the expected link group')
driver.write_text(source.replace(old, new))
PY
mv std std_first
mv logs/configure.log logs/configure_first.log
mkdir std
export CC=/work/tools/ccc CXX=/work/tools/cxx AR=x86_64-elf-ar RANLIB=x86_64-elf-ranlib LD=x86_64-elf-ld NM=x86_64-elf-nm OBJDUMP=x86_64-elf-objdump STRIP=x86_64-elf-strip
export CFLAGS='-O2 -g0 -fno-pic' CXXFLAGS='-O2 -g0 -fno-pic' gcc_cv_target_thread_file=posix
unset COMPILER_PATH LIBRARY_PATH CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH GCC_EXEC_PREFIX
cd /work/std
printf 'int main(void) { return 0; }\n' >xos_link_test.c
"$CC" xos_link_test.c -o xos_link_test
x86_64-elf-readelf -h xos_link_test
"$source/libstdc++-v3/configure" --build="$("$source/config.guess")" --host=x86_64-unknown-xos \
    --prefix=/usr --with-gxx-include-dir=/usr/include/c++/16.2.0 --disable-multilib --disable-shared --disable-nls \
    --disable-libstdcxx-pch --enable-libstdcxx-threads=yes --enable-clocale=generic \
    --disable-libstdcxx-backtrace --disable-libstdcxx-filesystem-ts 2>&1 | tee /work/logs/configure.log
grep -Eq '^#define _GLIBCXX_HAS_GTHREADS 1' config.h
make -j4 2>&1 | tee /work/logs/make.log
make install DESTDIR=/work/cxx-export 2>&1 | tee /work/logs/install.log
