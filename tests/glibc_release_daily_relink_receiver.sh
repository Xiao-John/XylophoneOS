#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run with a frozen material archive and target tools in a detached Linux environment.
set -euo pipefail
if [[ $# != 4 ]]; then
    printf 'Usage: %s ARCHIVE ARCHIVE_SHA256 MANIFEST_SHA256 OUTPUT\n' "$0" >&2
    exit 2
fi
archive=$1
archive_sha=$2
manifest_sha=$3
output=$4
export LC_ALL=C PYTHONDONTWRITEBYTECODE=1
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == "$archive_sha" ]]
mkdir "$output"
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
materials=$work/materials
mkdir "$materials"
tar -xzf "$archive" -C "$materials"

link() {
    python3 -B "$materials/tools/relink_release_daily.py" relink \
        --materials "$materials" --sha256 "$manifest_sha" "$@"
}
link --output "$output/original" > "$output/original.json"

libc=$materials/sysroot/usr/lib/libc.a
replacement=$work/libc.a
cp "$libc" "$replacement"
cat > "$work/observe_exit.c" <<'C'
extern long write(int, const void *, unsigned long);
extern _Noreturn void xos_relink_original_exit(int);

_Noreturn void exit(int status)
{
    static const char marker[] = "[DAILY_RELINK_EXIT]\n";
    (void)write(2, marker, sizeof(marker) - 1);
    xos_relink_original_exit(status);
}
C
x86_64-elf-ar p "$libc" exit.o > "$work/original_exit.o"
x86_64-elf-objcopy --redefine-sym exit=xos_relink_original_exit "$work/original_exit.o" "$work/renamed_exit.o"
x86_64-elf-gcc -O2 -nostdinc -fno-pie -fno-pic -mno-red-zone -ffunction-sections \
    -c "$work/observe_exit.c" -o "$work/observe_exit.o"
x86_64-elf-ld -r -z noexecstack -o "$work/exit.o" "$work/renamed_exit.o" "$work/observe_exit.o"
x86_64-elf-ar rD "$replacement" "$work/exit.o"
x86_64-elf-ranlib -D "$replacement"
PYTHONPATH="$materials/tools" python3 -B - "$libc" "$replacement" > "$output/archive_comparison.json" <<'PY'
import hashlib
import json
import sys

from archive_member_map import read_archive
from xypm_format import require, sha_file

original_path, replacement_path = sys.argv[1:]
original = read_archive(original_path)
replacement = read_archive(replacement_path)
require(list(original) == list(replacement), 'archive member order changed')
changed = [name for name in original if original[name] != replacement[name]]
require(changed == ['exit.o'], 'unexpected archive member changes')
print(json.dumps({
    'ordered_members_equal': len(original), 'changed_members': changed,
    'original_exit_object_sha256': hashlib.sha256(original['exit.o']).hexdigest(),
    'replacement_exit_object_sha256': hashlib.sha256(replacement['exit.o']).hexdigest(),
    'original_archive_sha256': sha_file(original_path),
    'replacement_archive_sha256': sha_file(replacement_path),
}, indent=2, sort_keys=True))
PY
replacement_sha=$(sha256sum "$replacement" | cut -d' ' -f1)
if link --output "$output/rejected" --libc "$replacement" --libc-sha256 "$archive_sha" > "$work/rejected.log" 2>&1; then
    printf 'Accepted an incorrect replacement digest\n' >&2
    exit 1
fi
grep -F 'replacement archive digest differs' "$work/rejected.log"
[[ ! -e "$output/rejected" ]]
link --output "$output/replacement" --libc "$replacement" --libc-sha256 "$replacement_sha" > "$output/replacement.json"
