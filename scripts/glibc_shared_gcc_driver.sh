#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Wrapper used only by the private, versioned GNU runtime build.
set -euo pipefail

case "${0##*/}" in
    cc) compiler=$XOS_TARGET_CC; language=() ;;
    cxx) compiler=$XOS_TARGET_CXX; language=(-nostdinc++) ;;
    *) exit 2 ;;
esac
lib=$XOS_C_SYSROOT/usr/lib
flags=(-B"$XOS_GCC_TOOLS/" --sysroot="$XOS_C_SYSROOT" -nostdinc
       -isystem "$XOS_C_SYSROOT/usr/include" -isystem "$lib/compiler-include"
       -mno-red-zone -Wa,--noexecstack -Werror=trampolines)
shared=no
shared_probe=no
for arg; do
    case "$arg" in
        -shared) shared=yes ;;
        -lgcc_s) shared_probe=yes ;;
        -[cSEM]|-MM|-fsyntax-only|-dump*|-print*|--version)
            exec "$compiler" "${flags[@]}" "${language[@]}" "$@" ;;
    esac
done

if [[ $shared == yes ]]; then
    before=() after=()
    if [[ "${0##*/}" == cxx ]]; then
        before=("$XOS_SHARED_GLIBC/csu/crti.o" "$XOS_GCC_PIC_CRT/crtbeginS.o")
        after=("$XOS_SHARED_GLIBC/stdlib/atexit.oS" -Wl,--as-needed,-l:libgcc_s.so.1,-l:libc.so.0.1,-l:ld.so.1
               "$XOS_GCC_PIC_CRT/crtendS.o" "$XOS_SHARED_GLIBC/csu/crtn.o")
    fi
    if [[ -n ${XOS_NATIVE_DYNAMIC_NOTE:-} ]]; then
        before+=("$XOS_NATIVE_DYNAMIC_NOTE")
    fi
    exec "$compiler" "${flags[@]}" "${language[@]}" -nostdlib \
        -Wl,-shared,--hash-style=both,--build-id=none,-z,noexecstack,-z,now,-z,relro,-z,max-page-size=8192,-z,separate-code,--eh-frame-hdr,-z,defs \
        -L"$XOS_GCC_LINK" -Wl,-rpath-link,"$XOS_GCC_LINK" "${before[@]}" "$@" "${after[@]}"
fi
if [[ $shared_probe == yes ]]; then
    # configure only links this probe. The pinned XOS interpreter is absent
    # on the host and the build must never attempt to run the probe.
    exec "$compiler" "${flags[@]}" "${language[@]}" -nostdlib -Wl,-pie,-e,_start,--no-dynamic-linker \
        -L"$XOS_GCC_LINK" -Wl,-rpath-link,"$XOS_GCC_LINK" "$XOS_SHARED_GLIBC/csu/Scrt1.o" "$@" -lc
fi
if [[ $# == 1 && $1 == -v ]]; then
    exec "$compiler" "${flags[@]}" "${language[@]}" "$@"
fi
exec "$compiler" "${flags[@]}" "${language[@]}" -static -no-pie -nostdlib \
    -Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096 "-T$XOS_C_SYSROOT/user.ld" \
    "$lib/xos_start.o" "$lib/crti.o" "$lib/crtbegin.o" "$lib/xos_start_c.o" "$@" \
    -Wl,--start-group "$lib/libc.a" "$lib/libm.a" "$lib/libxos_terminal.a" "$lib/libgcc.a" \
    -Wl,--end-group "$lib/crtend.o" "$lib/crtn.o"
