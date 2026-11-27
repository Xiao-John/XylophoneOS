#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run in an isolated Linux receiver with only the material archive and target tools.
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
actual=$(sha256sum "$archive" | cut -d' ' -f1)
[[ "$actual" == "$archive_sha" ]]
mkdir "$output"
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
materials=$work/materials
mkdir "$materials"
tar -xzf "$archive" -C "$materials"

link() {
    python3 "$materials/tools/relink_release_xypm.py" --program dash --materials "$materials" --sha256 "$manifest_sha" "$@"
}

link --output "$output/original.elf"
libc="$materials/sysroot/usr/lib/libc.a"
replacement="$work/libc.a"
cp "$libc" "$replacement"
cat > "$work/getpid.c" <<'C'
int __getpid(void)
{
    return 773355;
}

extern __typeof__(__getpid) getpid __attribute__((weak, alias("__getpid")));
C
x86_64-elf-gcc -O2 -nostdinc -fno-pie -fno-pic -mno-red-zone -ffunction-sections -c "$work/getpid.c" -o "$work/getpid.o"
x86_64-elf-ar rD "$replacement" "$work/getpid.o"
x86_64-elf-ranlib -D "$replacement"
x86_64-elf-ar t "$libc" > "$work/original.members"
x86_64-elf-ar t "$replacement" > "$work/replacement.members"
cmp "$work/original.members" "$work/replacement.members"
[[ "$(grep -xc getpid.o "$work/original.members")" == 1 ]]
[[ -z "$(sort "$work/original.members" | uniq -d)" ]]

member_digests() (
    directory=$1
    mkdir "$directory"
    cd "$directory"
    x86_64-elf-ar x "$2"
    sha256sum -- *
)
member_digests "$work/original-members" "$libc" > "$work/original.sha"
member_digests "$work/replacement-members" "$replacement" > "$work/replacement.sha"
difference="$(diff -U0 "$work/original.sha" "$work/replacement.sha")" || [[ "$?" == 1 ]]
[[ "$(printf '%s\n' "$difference" | grep -Ec '^[+-][0-9a-f]{64}  getpid[.]o$')" == 2 ]]
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
