#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Replay the original GNU Make link and qualify an isolated replacement libc.
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
    python3 -B "$materials/tools/relink_release_xypm.py" --program make \
        --materials "$materials" --sha256 "$manifest_sha" "$@"
}
link --output "$output/original.elf"

libc=$materials/sysroot/usr/lib/libc.a
replacement=$work/libc.a
cp "$libc" "$replacement"
cat > "$work/observe_exit.c" <<'C'
extern long write(int, const void *, unsigned long);
extern _Noreturn void xos_relink_original_exit(int);

_Noreturn void exit(int status)
{
    static const char marker[] = "[GMAKE_RELINK_EXIT]\n";
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

x86_64-elf-ar t "$libc" > "$work/original.members"
x86_64-elf-ar t "$replacement" > "$work/replacement.members"
cmp "$work/original.members" "$work/replacement.members"
[[ "$(grep -xc exit.o "$work/original.members")" == 1 ]]
[[ -z "$(sort "$work/original.members" | uniq -d)" ]]
member_digests() (
    mkdir "$1"
    cd "$1"
    x86_64-elf-ar x "$2"
    sha256sum -- *
)
member_digests "$work/original-members" "$libc" > "$work/original.sha"
member_digests "$work/replacement-members" "$replacement" > "$work/replacement.sha"
difference="$(diff -U0 "$work/original.sha" "$work/replacement.sha")" || [[ "$?" == 1 ]]
[[ "$(printf '%s\n' "$difference" | grep -Ec '^[+-][0-9a-f]{64}  exit[.]o$')" == 2 ]]
[[ "$(printf '%s\n' "$difference" | grep -Ec '^[+-][0-9a-f]{64}  ')" == 2 ]]
printf '%s\n' "$difference" | grep -E '^[+-][0-9a-f]{64}  '
printf 'ordered_archive_members=%s\n' "$(grep -c . "$work/original.members")"

replacement_sha=$(sha256sum "$replacement" | cut -d' ' -f1)
printf 'replacement_libc=%s\n' "$replacement_sha"
if link --output "$output/rejected.elf" --libc "$replacement" --libc-sha256 "$archive_sha" > "$work/rejected.log" 2>&1; then
    printf 'Accepted an incorrect replacement archive digest\n' >&2
    exit 1
fi
grep -F 'replacement archive digest differs' "$work/rejected.log"
[[ ! -e "$output/rejected.elf" ]]
link --output "$output/replacement.elf" --libc "$replacement" --libc-sha256 "$replacement_sha"
