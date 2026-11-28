#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Reproduce the released xypm and modify one libc member in a detached receiver.
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
    python3 -B "$materials/tools/relink_release_xypm.py" \
        --materials "$materials" --sha256 "$manifest_sha" "$@"
}
link --output "$output/original.elf" > "$output/original.sha256"

libc=$materials/sysroot/usr/lib/libc.a
replacement=$work/libc.a
cp "$libc" "$replacement"
# Preserve the original implementation and its unwind/locking behavior. The
# replacement member adds an observable prefix only to xypm's version line.
cat > "$output/observe_puts.c" <<'C'
extern long write(int, const void *, unsigned long);
extern int xos_relink_original_puts(const char *);

int _IO_puts(const char *text)
{
    static const char version[] = "xypm 0.4.0 (P3 offline repositories)";
    static const char marker[] = "[REPLACED_LIBC]\n";
    const char *left = text, *right = version;
    while (*left && *left == *right) { ++left; ++right; }
    if (!*left && !*right) (void)write(1, marker, sizeof(marker) - 1);
    return xos_relink_original_puts(text);
}
extern __typeof(_IO_puts) puts __attribute__((weak, alias("_IO_puts")));
C
x86_64-elf-ar p "$libc" ioputs.o > "$work/original_ioputs.o"
x86_64-elf-objcopy --redefine-sym _IO_puts=xos_relink_original_puts \
    --redefine-sym puts=xos_relink_original_puts_alias \
    "$work/original_ioputs.o" "$work/renamed_ioputs.o"
x86_64-elf-gcc -O2 -nostdinc -fno-pie -fno-pic -mno-red-zone -ffunction-sections \
    -c "$output/observe_puts.c" -o "$work/observe_puts.o"
x86_64-elf-ld -r -z noexecstack -o "$work/ioputs.o" \
    "$work/renamed_ioputs.o" "$work/observe_puts.o"
x86_64-elf-ar rD "$replacement" "$work/ioputs.o"
x86_64-elf-ranlib -D "$replacement"

x86_64-elf-ar t "$libc" > "$output/original.members"
x86_64-elf-ar t "$replacement" > "$output/replacement.members"
cmp "$output/original.members" "$output/replacement.members"
[[ "$(grep -xc ioputs.o "$output/original.members")" == 1 ]]
[[ -z "$(sort "$output/original.members" | uniq -d)" ]]
member_digests() (
    mkdir "$1"
    cd "$1"
    x86_64-elf-ar x "$2"
    sha256sum -- *
)
member_digests "$work/original-members" "$libc" > "$output/original_member_sha256.txt"
member_digests "$work/replacement-members" "$replacement" > "$output/replacement_member_sha256.txt"
difference="$(diff -U0 "$output/original_member_sha256.txt" "$output/replacement_member_sha256.txt")" || [[ "$?" == 1 ]]
[[ "$(printf '%s\n' "$difference" | grep -Ec '^[+-][0-9a-f]{64}  ioputs[.]o$')" == 2 ]]
[[ "$(printf '%s\n' "$difference" | grep -Ec '^[+-][0-9a-f]{64}  ')" == 2 ]]
printf '%s\n' "$difference" > "$output/changed_member.diff"
replacement_sha=$(sha256sum "$replacement" | cut -d' ' -f1)
printf '%s\n' "$replacement_sha" > "$output/replacement_libc.sha256"

wrong_sha=$(printf '%064d' 0)
[[ "$manifest_sha" != "$wrong_sha" && "$replacement_sha" != "$wrong_sha" ]]
if python3 -B "$materials/tools/relink_release_xypm.py" \
    --materials "$materials" --sha256 "$wrong_sha" \
    --output "$output/rejected_materials.elf" > "$output/rejected_materials.log" 2>&1; then
    printf 'Accepted an incorrect materials digest\n' >&2
    exit 1
fi
grep -F 'materials manifest differs' "$output/rejected_materials.log"
[[ ! -e "$output/rejected_materials.elf" ]]
if link --output "$output/rejected.elf" --libc "$replacement" \
    --libc-sha256 "$wrong_sha" > "$output/rejected_libc.log" 2>&1; then
    printf 'Accepted an incorrect replacement digest\n' >&2
    exit 1
fi
grep -F 'replacement archive digest differs' "$output/rejected_libc.log"
[[ ! -e "$output/rejected.elf" ]]
link --output "$output/replacement.elf" --libc "$replacement" \
    --libc-sha256 "$replacement_sha" > "$output/replacement.sha256"
printf 'PASS detached xypm original and single-member libc replacement\n'
