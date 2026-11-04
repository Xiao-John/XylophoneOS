# Build command record

Commands below are grouped by dependency stage, not a claim that every operation ran sequentially. GCC/Qt used at most 4 jobs, QEMU 2, with at most 6 combined. No guest was run by this packager.

Paths in this export and the archive are configurable templates, not verbatim historical command bytes. `derived/top-level-commands.json` is a readable index of those records. The two reconstructed/retained outer invocations are explicitly labelled; they are not a fabricated command transcript.

```sh
cd ${XOS_ROOT}
source .cache/ssg_p2f/env.sh
```

## nasm-configure

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/sources/nasm-3.02
${XOS_ROOT}/.cache/ssg_p2f/sources/nasm-3.02/configure --prefix=${XOS_ROOT}/.cache/ssg_p2f/prefix
```

## nasm-build

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/sources/nasm-3.02
make -j4
```

## nasm-install

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/sources/nasm-3.02
make install
```

## binutils-configure

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/build/binutils
${XOS_ROOT}/.cache/ssg_p2f/sources/binutils-2.47/configure --target=x86_64-elf --prefix=${XOS_ROOT}/.cache/ssg_p2f/prefix --with-sysroot --disable-nls --disable-werror --disable-multilib
```

## binutils-build

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/build/binutils
make -j4
```

## binutils-install

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/build/binutils
make install
```

## gcc-configure

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/build/gcc
${XOS_ROOT}/.cache/ssg_p2f/sources/gcc-16.2.0/configure --target=x86_64-elf --prefix=${XOS_ROOT}/.cache/ssg_p2f/prefix --disable-nls --enable-languages=c,c++ --without-headers --disable-multilib --disable-shared --disable-bootstrap --disable-libssp --disable-libquadmath --disable-libgomp --disable-libatomic
```

## gcc-build

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/build/gcc
make -j4 all-gcc all-target-libgcc
```

## gcc-install

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/build/gcc
make install-gcc install-target-libgcc
```

## qemu-configure

Evidence: `.cache/ssg_p2f/logs/qemu-configure-command.json`. Provenance: recorded.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/build/qemu
${XOS_ROOT}/.cache/ssg_p2f/sources/qemu-11.1.2/configure --prefix=${XOS_ROOT}/.cache/ssg_p2f/qemu-prefix --target-list=x86_64-softmmu --disable-user --disable-docs --disable-guest-agent --disable-tools --disable-slirp --disable-gtk --disable-sdl --disable-opengl --disable-vnc --disable-curses --disable-spice --disable-rust --disable-werror --enable-download --audio-drv-list=
```

## qemu-build

Evidence: `.cache/ssg_p2f/logs/qemu-build-receipt.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/build/qemu
ninja -j2 qemu-system-x86_64
```

## qemu-install

Evidence: `.cache/ssg_p2f/logs/qemu-build-receipt.json`. Provenance: recorded. Recorded return code: `1`.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/build/qemu
ninja -j2 install
```

## qemu-install-after-byte-restoration

Evidence: `.cache/ssg_p2f/logs/qemu-install-retry-receipt.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}/.cache/ssg_p2f/build/qemu
ninja -j2 install
```

## qt-source-preparation

Evidence: `.cache/ssg_p2f/logs/qt-prepare-source.log`. Provenance: equivalent invocation reconstructed from preserved paths and builder interface.

```sh
cd ${XOS_ROOT}
python3 src/ports/qt6/prepare_source.py .cache/ssg_p2f/downloads/qtbase-everywhere-src-6.8.3.tar.xz .cache/ssg_p2f/qt-target-source
```

## system

Evidence: `build/ssg_p2f/system/manifest.json`. Provenance: outer invocation retained in build handoff; internal argv arrays in original manifest.

```sh
cd ${XOS_ROOT}
python3 scripts/build.py --output-dir build/ssg_p2f/system
```

## threading-newlib

Evidence: `.cache/ssg_p2f/logs/runtime-build.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}
${XOS_PYTHON} ${XOS_ROOT}/scripts/build_threading_newlib.py --archive ${XOS_ROOT}/.cache/ssg_p2f/downloads/newlib-4.6.0.20260123.tar.gz --output ${XOS_ROOT}/.cache/ssg_p2f/threading_newlib --jobs 4
```

## threading-sdk

Evidence: `.cache/ssg_p2f/logs/runtime-build.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}
${XOS_PYTHON} ${XOS_ROOT}/scripts/build_threading_sdk.py --newlib-prefix ${XOS_ROOT}/.cache/ssg_p2f/threading_newlib/prefix --gcc-source ${XOS_ROOT}/.cache/ssg_p2f/sources/gcc-16.2.0 --cpp --jobs 4 --output ${XOS_ROOT}/build/ssg_p2f/sdk
```

## qt-target-configure

Evidence: `.cache/ssg_p2f/logs/runtime-build.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}
${XOS_PYTHON} ${XOS_ROOT}/src/ports/qt6/configure_widgets.py --source ${XOS_ROOT}/.cache/ssg_p2f/qt-target-source --build ${XOS_ROOT}/build/ssg_p2f/qt-widgets --sdk ${XOS_ROOT}/build/ssg_p2f/sdk --binutils ${XOS_ROOT}/.cache/ssg_p2f/target-tools --host-qt ${XOS_ROOT}/.cache/ssg_p2f/host-qt-official
```

## qt-target-build

Evidence: `.cache/ssg_p2f/logs/runtime-build.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}
cmake --build ${XOS_ROOT}/build/ssg_p2f/qt-widgets --target Widgets --parallel 4
```

## payloads

Evidence: `.cache/ssg_p2f/logs/payloads-build.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}
${XOS_PYTHON} ${XOS_ROOT}/scripts/build_ssg_p1.py --sdk ${XOS_ROOT}/build/ssg_p2f/sdk --qt-build ${XOS_ROOT}/build/ssg_p2f/qt-widgets --qt-source ${XOS_ROOT}/.cache/ssg_p2f/qt-target-source --host-qt ${XOS_ROOT}/.cache/ssg_p2f/host-qt-official --binutils ${XOS_ROOT}/.cache/ssg_p2f/target-tools --output ${XOS_ROOT}/build/ssg_p2f/payloads
```

## oracle-browser

Evidence: `.cache/ssg_p2f/logs/payloads-build.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd ${XOS_ROOT}
${XOS_PYTHON} ${XOS_ROOT}/src/ports/aurora_browser/build.py --sdk ${XOS_ROOT}/build/ssg_p2f/sdk --qt-build ${XOS_ROOT}/build/ssg_p2f/qt-widgets --qt-source ${XOS_ROOT}/.cache/ssg_p2f/qt-target-source --host-qt ${XOS_ROOT}/.cache/ssg_p2f/host-qt-official --binutils ${XOS_ROOT}/.cache/ssg_p2f/target-tools --test-structure-oracle --output ${XOS_ROOT}/build/ssg_p2f/oracle-browser/browser.elf
```

## payload-component-1

Evidence: `build/ssg_p2f/payloads/manifest.json`. Provenance: recorded.

```sh
cd ${XOS_ROOT}
${XOS_PYTHON} ${XOS_ROOT}/build/ssg_p2f/sdk/compile.py ${XOS_ROOT}/src/user/apps/ssg_session.cpp -o ${XOS_ROOT}/build/ssg_p2f/payloads/session.elf
```

## payload-component-2

Evidence: `build/ssg_p2f/payloads/manifest.json`. Provenance: recorded.

```sh
cd ${XOS_ROOT}
${XOS_PYTHON} ${XOS_ROOT}/src/ports/qt6/build_fixture.py --source ${XOS_ROOT}/src/user/apps/ssg_consumer.cpp --qrc ${XOS_ROOT}/tests/fixtures/qt6/resources.qrc --sdk ${XOS_ROOT}/build/ssg_p2f/sdk --qt-build ${XOS_ROOT}/build/ssg_p2f/qt-widgets --host-qt ${XOS_ROOT}/.cache/ssg_p2f/host-qt-official --binutils ${XOS_ROOT}/.cache/ssg_p2f/target-tools --output ${XOS_ROOT}/build/ssg_p2f/payloads/consumer/ssg-consumer.elf
```

## payload-component-3

Evidence: `build/ssg_p2f/payloads/manifest.json`. Provenance: recorded.

```sh
cd ${XOS_ROOT}
${XOS_PYTHON} ${XOS_ROOT}/src/ports/qt6/build_widgets_fixture.py --source ${XOS_ROOT}/src/ports/qt6/editor/main.cpp --sdk ${XOS_ROOT}/build/ssg_p2f/sdk --qt-build ${XOS_ROOT}/build/ssg_p2f/qt-widgets --qt-source ${XOS_ROOT}/.cache/ssg_p2f/qt-target-source --core-build ${XOS_ROOT}/build/ssg_p2f/qt-widgets --host-qt ${XOS_ROOT}/.cache/ssg_p2f/host-qt-official --binutils ${XOS_ROOT}/.cache/ssg_p2f/target-tools --output ${XOS_ROOT}/build/ssg_p2f/payloads/notes/notes.elf
```

## payload-component-4

Evidence: `build/ssg_p2f/payloads/manifest.json`. Provenance: recorded.

```sh
cd ${XOS_ROOT}
${XOS_PYTHON} ${XOS_ROOT}/src/ports/aurora_browser/build.py --sdk ${XOS_ROOT}/build/ssg_p2f/sdk --qt-build ${XOS_ROOT}/build/ssg_p2f/qt-widgets --qt-source ${XOS_ROOT}/.cache/ssg_p2f/qt-target-source --host-qt ${XOS_ROOT}/.cache/ssg_p2f/host-qt-official --binutils ${XOS_ROOT}/.cache/ssg_p2f/target-tools --output ${XOS_ROOT}/build/ssg_p2f/payloads/browser/browser.elf
```

## Full internal commands

The original system and SDK manifests and all component receipts contain the compile/link argument arrays. `build/ssg_p2f/sdk/compile.py` accompanies the Session command. Qt's `build.ninja`, `CMakeFiles/rules.ninja` and `CMakeCache.txt`, plus QEMU's `build.ninja` and configuration files, preserve generated command details. All configure/build/install stdout/stderr logs are included without truncation.

## Preparation records

Official source URLs, hashes, host Qt metadata and extraction logs are under `.cache/ssg_p2f/downloads/` and `.cache/ssg_p2f/logs/` in the archive. The three task-local orchestration scripts and `env.sh` are included. Host package installation logs are preserved; they are not a complete shell-session transcript. The host Qt ICU symlink layout and QEMU source-byte restoration are documented in their original JSON receipts.
