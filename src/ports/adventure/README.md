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
