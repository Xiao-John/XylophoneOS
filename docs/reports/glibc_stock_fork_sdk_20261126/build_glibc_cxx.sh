#!/usr/bin/env bash
set -euo pipefail
cd /work
mkdir -p logs upstream std libgcc tools
archive=/work/material/gcc-16.2.0.tar.xz
pinned=e6738e29597f733270731aa90600f37ffdc045079dfc27ec7e8192cc81085c3e
signer=7F74F97C103468EE5D750B583AB00996FC26A641
printf '%s  %s\n' "$pinned" "$archive" | sha256sum -c -
gpgv --keyring /work/material/gnu-keyring.gpg --status-fd 1 "$archive.sig" "$archive" >logs/gpgv.status 2>logs/gpgv.log
cat logs/gpgv.log
grep -q "^\[GNUPG:\] VALIDSIG $signer " logs/gpgv.status
if grep -Eq '^\[GNUPG:\] (BADSIG|ERRSIG|EXPKEYSIG|REVKEYSIG|KEYEXPIRED|SIGEXPIRED|EXPSIG) ' logs/gpgv.status; then exit 2; fi
tar -xJf "$archive" --strip-components=1 -C upstream
printf '%s  %s\n' "$pinned" "$archive" | sha256sum -c -
source=/work/upstream
sdk=/work/sdk/sysroot
python3 - "$source" <<'PY'
import re, sys
from pathlib import Path
root=Path(sys.argv[1])
sub=root/'config.sub'
text=sub.read_text()
assert text.count('| fiwix* )') == 1
sub.write_text(text.replace('| fiwix* )', '| fiwix* | xos )'))
for path in (root/'libstdc++-v3'/'crossconfig.m4',root/'libstdc++-v3'/'configure'):
    text=path.read_text()
    host='*-linux* | *-uclinux* | *-gnu* | *-kfreebsd*-gnu | *-cygwin* | *-solaris*)'
    assert text.count(host)==1, path
    start=text.index(host)
    end=text.index('\n    ;;',start)
    case=text[start:end].replace(host, '*-xos | '+host)
    statements=[]
    for line in case.splitlines(keepends=True):
        if re.search(r'(?:AC_DEFINE\(|#define )_GLIBCXX_USE_(?:DEV_RANDOM|RANDOM_TR1)\b',line):
            statements.extend(['    if test "$host_os" != xos; then\n', line, '    fi\n'])
        else:
            statements.append(line)
    path.write_text(text[:start]+''.join(statements)+text[end:])
PY
"$source/config.sub" x86_64-unknown-xos
cp "$source/libgcc/gthr-posix.h" libgcc/gthr-default.h
ln -s "$(command -v x86_64-elf-as)" tools/as
ln -s "$(command -v x86_64-elf-ld)" tools/ld
cat >tools/driver <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
sdk=/work/sdk/sysroot
lib=$sdk/usr/lib
base=${0##*/}
case "$base" in
  ccc) compiler=x86_64-elf-gcc; language=() ;;
  cxx) compiler=x86_64-elf-g++; language=(-nostdinc++);;
  *) exit 2 ;;
esac
flags=(-B/work/tools/ "--sysroot=$sdk" -nostdinc -isystem "$sdk/usr/include" -isystem "$lib/compiler-include" -mno-red-zone -ftls-model=local-exec -fno-pie)
for arg; do
  case "$arg" in
    -[cSEM]|-MM|-fsyntax-only|-dump*|-print*|--version|-v) exec "$compiler" "${flags[@]}" "${language[@]}" "$@" ;;
  esac
done
exec "$compiler" "${flags[@]}" "${language[@]}" -static -no-pie -nostdlib -Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096 "-T$sdk/user.ld" \
    "$lib/xos_start.o" "$lib/crti.o" "$lib/crtbegin.o" "$lib/xos_start_c.o" "$@" \
    -Wl,--start-group "$lib/libc.a" "$lib/libm.a" "$lib/libgcc.a" -Wl,--end-group "$lib/crtend.o" "$lib/crtn.o"
WRAP
chmod 755 tools/driver
ln -s driver tools/ccc
ln -s driver tools/cxx
export CC=/work/tools/ccc CXX=/work/tools/cxx AR=x86_64-elf-ar RANLIB=x86_64-elf-ranlib LD=x86_64-elf-ld NM=x86_64-elf-nm OBJDUMP=x86_64-elf-objdump STRIP=x86_64-elf-strip
export CFLAGS='-O2 -g0 -fno-pic' CXXFLAGS='-O2 -g0 -fno-pic' gcc_cv_target_thread_file=posix
unset COMPILER_PATH LIBRARY_PATH CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH GCC_EXEC_PREFIX
cd /work/std
"$source/libstdc++-v3/configure" --build="$("$source/config.guess")" --host=x86_64-unknown-xos \
  --prefix=/usr --with-gxx-include-dir=/usr/include/c++/16.2.0 --disable-multilib --disable-shared --disable-nls \
  --disable-libstdcxx-pch --enable-libstdcxx-threads=yes --enable-clocale=generic \
  --disable-libstdcxx-backtrace --disable-libstdcxx-filesystem-ts 2>&1 | tee /work/logs/configure.log
if ! grep -Eq '^#define _GLIBCXX_HAS_GTHREADS 1' config.h; then
  echo 'POSIX target gthreads is not active in candidate config' >&2
  exit 1
fi
make -j4 2>&1 | tee /work/logs/make.log
make install DESTDIR=/work/cxx-export 2>&1 | tee /work/logs/install.log
