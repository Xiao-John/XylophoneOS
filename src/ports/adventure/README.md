# Open Adventure for XOS

Open Adventure 1.12 (Colossal Cave), with a static XOS port that builds
**inside XOS**: Python generates `dungeon.c/h` from `adventure.yaml` using a
minimal `yaml` module, then the native GCC toolchain links the game.

## Build inside XOS

```sh
sh /src/open-adventure/build.sh
/out/advent
```

`build.sh` needs:

- `/usr/bin/python3` with the minimal standard library (`encodings`, `codecs`,
  `linecache`, `os`, `posixpath`, `genericpath`, `stat`, `abc`,
  `_collections_abc`, `warnings`);
- `/src/open-adventure/yaml.py` next to `make_dungeon.py`;
- `/sysroot` and the native `x86_64-elf-gcc/g++` tools.

No `make`, shell glob, libedit, or host-generated `dungeon.c/h` is used.

## Layout

```text
source_lock.json          archive SHA256, license, generated-data hashes
patches/0001_xos_runtime.patch
                          absolute UTF-8 generator paths, fixed seed,
                          zero save timestamp, no SIGINT
adventure.yaml            translated display strings; English vocabulary
xos/yaml.py               PyYAML subset used by make_dungeon.py
xos_readline.cpp          readline/add_history shim using XOS console reads
include/editline/readline.h
build.sh                  in-XOS build
upstream/COPYING          upstream license text
```

## Current limits

- The first batch translates startup, start room, class/score text and the
  lamp/keys/chest/coin names; most other room text remains English.
- `yaml.py` supports only the constructs used by this frozen file; it rejects
  everything else instead of guessing.
- No DOS/ANSI wrapping, locale, or Chinese display-width layout.
- `suspend`/`resume` and scripted save files are not part of the first gate.

Upstream code remains BSD-2-Clause; this port's new build/glue files are
Apache-2.0. Generated `dungeon.c/h` are data, not hand-edited source.

## XYPM package preparation

The package identity is `games.open_adventure`, with the executable at
`/usr/bin/advent`. `scripts/package_open_adventure.py` requires an existing
XOS-built ELF, its explicit build receipt, and a frozen SDK registered to the
selected xypm profile. It checks the ELF layout, source/input hashes and SDK
snapshot, then packages the executable, receipt and license materials. The
package does not install Python or the compiler, and does not grant process
construction permissions. The archive is an input for building, not a runtime
package dependency. The profile check is not proof of execution or authorship.

Produce `advent`, `dungeon.c` and `dungeon.h` with the documented **in-XOS**
build using the same registered SDK. Keep the actual image, toolchain and
source provenance; the old ADV0 report did not retain the ELF or bind it to a
package SDK. After exporting those files, record the observed hashes and the
actual build environment (the following arguments are placeholders to replace
with real information):

```sh
python3 scripts/record_open_adventure_build.py \
  --elf /path/to/advent --generated-c /path/to/dungeon.c \
  --generated-h /path/to/dungeon.h --archive /path/to/open-adventure-1.12.tar.gz \
  --sdk /path/to/frozen_sdk --profile /path/to/profile.json \
  --build-environment 'actual XOS image digest and build invocation' \
  --compiler 'actual compiler version and seed receipt' -o /path/to/build_receipt.json
python3 scripts/package_open_adventure.py --elf /path/to/advent \
  --build-receipt /path/to/build_receipt.json --sdk /path/to/frozen_sdk \
  --profile /path/to/profile.json -o /path/to/open_adventure.xpk
```

The recorder only observes files after the build: the operator-supplied
compiler, image and SDK linkage are not independently authenticated. Retain
build logs and the actual target inputs for review. After all changes are
committed, verify the package with xypm, install on a private offline candidate
image, run the installed game and separately check uninstall/preservation and
error cases. Guest-side mutating xypm installation is not yet implemented.
