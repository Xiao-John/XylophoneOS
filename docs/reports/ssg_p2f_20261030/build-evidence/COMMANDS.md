# Build command record

Commands below are grouped by dependency stage, not a claim that every operation ran sequentially. GCC/Qt used at most 4 jobs, QEMU 2, with at most 6 combined. No guest was run by this packager.

Original absolute paths and argument arrays remain in the archive. `derived/top-level-commands.json` is a readable index of those records. The two reconstructed/retained outer invocations are explicitly labelled; they are not a fabricated command transcript.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
source .cache/ssg_p2f/env.sh
```

## nasm-configure

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/sources/nasm-3.02
/workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/sources/nasm-3.02/configure --prefix=/workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/prefix
```

## nasm-build

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/sources/nasm-3.02
make -j4
```

## nasm-install

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/sources/nasm-3.02
make install
```

## binutils-configure

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/build/binutils
/workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/sources/binutils-2.47/configure --target=x86_64-elf --prefix=/workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/prefix --with-sysroot --disable-nls --disable-werror --disable-multilib
```

## binutils-build

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/build/binutils
make -j4
```

## binutils-install

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/build/binutils
make install
```

## gcc-configure

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/build/gcc
/workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/sources/gcc-16.2.0/configure --target=x86_64-elf --prefix=/workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/prefix --disable-nls --enable-languages=c,c++ --without-headers --disable-multilib --disable-shared --disable-bootstrap --disable-libssp --disable-libquadmath --disable-libgomp --disable-libatomic
```

## gcc-build

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/build/gcc
make -j4 all-gcc all-target-libgcc
```

## gcc-install

Evidence: `.cache/ssg_p2f/logs/bootstrap-tools.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/build/gcc
make install-gcc install-target-libgcc
```

## qemu-configure

Evidence: `.cache/ssg_p2f/logs/qemu-configure-command.json`. Provenance: recorded.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/build/qemu
/workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/sources/qemu-11.1.2/configure --prefix=/workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/qemu-prefix --target-list=x86_64-softmmu --disable-user --disable-docs --disable-guest-agent --disable-tools --disable-slirp --disable-gtk --disable-sdl --disable-opengl --disable-vnc --disable-curses --disable-spice --disable-rust --disable-werror --enable-download --audio-drv-list=
```

## qemu-build

Evidence: `.cache/ssg_p2f/logs/qemu-build-receipt.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/build/qemu
ninja -j2 qemu-system-x86_64
```

## qemu-install

Evidence: `.cache/ssg_p2f/logs/qemu-build-receipt.json`. Provenance: recorded. Recorded return code: `1`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/build/qemu
ninja -j2 install
```

## qemu-install-after-byte-restoration

Evidence: `.cache/ssg_p2f/logs/qemu-install-retry-receipt.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/build/qemu
ninja -j2 install
```

## qt-source-preparation

Evidence: `.cache/ssg_p2f/logs/qt-prepare-source.log`. Provenance: equivalent invocation reconstructed from preserved paths and builder interface.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
python3 src/ports/qt6/prepare_source.py .cache/ssg_p2f/downloads/qtbase-everywhere-src-6.8.3.tar.xz .cache/ssg_p2f/qt-target-source
```

## system

Evidence: `build/ssg_p2f/system/manifest.json`. Provenance: outer invocation retained in build handoff; internal argv arrays in original manifest.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
python3 scripts/build.py --output-dir build/ssg_p2f/system
```

## threading-newlib

Evidence: `.cache/ssg_p2f/logs/runtime-build.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/77fc8ad4822d/XylophoneOS/scripts/build_threading_newlib.py --archive /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/downloads/newlib-4.6.0.20260123.tar.gz --output /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/threading_newlib --jobs 4
```

## threading-sdk

Evidence: `.cache/ssg_p2f/logs/runtime-build.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/77fc8ad4822d/XylophoneOS/scripts/build_threading_sdk.py --newlib-prefix /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/threading_newlib/prefix --gcc-source /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/sources/gcc-16.2.0 --cpp --jobs 4 --output /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/sdk
```

## qt-target-configure

Evidence: `.cache/ssg_p2f/logs/runtime-build.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/77fc8ad4822d/XylophoneOS/src/ports/qt6/configure_widgets.py --source /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/qt-target-source --build /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/qt-widgets --sdk /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/sdk --binutils /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/target-tools --host-qt /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/host-qt-official
```

## qt-target-build

Evidence: `.cache/ssg_p2f/logs/runtime-build.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
cmake --build /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/qt-widgets --target Widgets --parallel 4
```

## payloads

Evidence: `.cache/ssg_p2f/logs/payloads-build.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/77fc8ad4822d/XylophoneOS/scripts/build_ssg_p1.py --sdk /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/sdk --qt-build /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/qt-widgets --qt-source /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/qt-target-source --host-qt /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/host-qt-official --binutils /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/target-tools --output /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/payloads
```

## oracle-browser

Evidence: `.cache/ssg_p2f/logs/payloads-build.json`. Provenance: recorded. Recorded return code: `0`.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/77fc8ad4822d/XylophoneOS/src/ports/aurora_browser/build.py --sdk /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/sdk --qt-build /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/qt-widgets --qt-source /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/qt-target-source --host-qt /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/host-qt-official --binutils /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/target-tools --test-structure-oracle --output /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/oracle-browser/browser.elf
```

## payload-component-1

Evidence: `build/ssg_p2f/payloads/manifest.json`. Provenance: recorded.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/sdk/compile.py /workspace/scratch/77fc8ad4822d/XylophoneOS/src/user/apps/ssg_session.cpp -o /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/payloads/session.elf
```

## payload-component-2

Evidence: `build/ssg_p2f/payloads/manifest.json`. Provenance: recorded.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/77fc8ad4822d/XylophoneOS/src/ports/qt6/build_fixture.py --source /workspace/scratch/77fc8ad4822d/XylophoneOS/src/user/apps/ssg_consumer.cpp --qrc /workspace/scratch/77fc8ad4822d/XylophoneOS/tests/fixtures/qt6/resources.qrc --sdk /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/sdk --qt-build /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/qt-widgets --host-qt /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/host-qt-official --binutils /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/target-tools --output /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/payloads/consumer/ssg-consumer.elf
```

## payload-component-3

Evidence: `build/ssg_p2f/payloads/manifest.json`. Provenance: recorded.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/77fc8ad4822d/XylophoneOS/src/ports/qt6/build_widgets_fixture.py --source /workspace/scratch/77fc8ad4822d/XylophoneOS/src/ports/qt6/editor/main.cpp --sdk /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/sdk --qt-build /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/qt-widgets --qt-source /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/qt-target-source --core-build /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/qt-widgets --host-qt /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/host-qt-official --binutils /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/target-tools --output /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/payloads/notes/notes.elf
```

## payload-component-4

Evidence: `build/ssg_p2f/payloads/manifest.json`. Provenance: recorded.

```sh
cd /workspace/scratch/77fc8ad4822d/XylophoneOS
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3 /workspace/scratch/77fc8ad4822d/XylophoneOS/src/ports/aurora_browser/build.py --sdk /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/sdk --qt-build /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/qt-widgets --qt-source /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/qt-target-source --host-qt /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/host-qt-official --binutils /workspace/scratch/77fc8ad4822d/XylophoneOS/.cache/ssg_p2f/target-tools --output /workspace/scratch/77fc8ad4822d/XylophoneOS/build/ssg_p2f/payloads/browser/browser.elf
```

## Full internal commands

The original system and SDK manifests and all component receipts contain the compile/link argument arrays. `build/ssg_p2f/sdk/compile.py` accompanies the Session command. Qt's `build.ninja`, `CMakeFiles/rules.ninja` and `CMakeCache.txt`, plus QEMU's `build.ninja` and configuration files, preserve generated command details. All configure/build/install stdout/stderr logs are included without truncation.

## Preparation records

Official source URLs, hashes, host Qt metadata and extraction logs are under `.cache/ssg_p2f/downloads/` and `.cache/ssg_p2f/logs/` in the archive. The three task-local orchestration scripts and `env.sh` are included. Host package installation logs are preserved; they are not a complete shell-session transcript. The host Qt ICU symlink layout and QEMU source-byte restoration are documented in their original JSON receipts.
