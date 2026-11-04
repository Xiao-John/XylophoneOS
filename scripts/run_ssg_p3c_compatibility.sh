#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Recheck the existing P3B modes on the new supervisor binary.
set -u
if [ "$#" -ne 3 ]; then
    printf 'Usage: %s P3C_BUILD P3B_BUILD FRESH_OUTPUT\n' "$0" >&2
    exit 2
fi
: "${QEMU:?Set QEMU to the QEMU executable}"
: "${XOS_IMAGE:?Set XOS_IMAGE to the read-only XOS image}"
xos_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$xos_root" || exit 2
xos_build=$1
xos_p3b=$2
xos_out=$3
python3 - "$xos_out" <<'PY' || exit 2
from pathlib import Path
import sys
root = (Path.cwd() / 'build').resolve()
out = Path(sys.argv[1]).resolve()
if not out.is_relative_to(root) or out.exists():
    raise SystemExit('Choose a fresh output directory under build/')
out.mkdir(parents=True)
PY
failures=0
for test_case in edit revoke protect-document protect-ancestor; do
    python3 tests/ssg_p3b_guest.py --image "$XOS_IMAGE" --supervisor "$xos_build/supervisor-test/supervisor-test.elf" \
        --browser "$xos_p3b/browser-test/browser.elf" --notes "$xos_p3b/notes-test/notes.elf" \
        --input tests/fixtures/ssg_browser/p2f.html --case "$test_case" --output "$xos_out/$test_case" > "$xos_out/$test_case.run.log" 2>&1
    guest=$?
    verify=99
    if [ "$guest" -eq 0 ]; then
        python3 tests/ssg_p3b_dynamic_verify.py "$xos_out/$test_case" --browser-receipt "$xos_p3b/browser-test/browser.portable.receipt.json" > "$xos_out/$test_case.verify.log" 2>&1
        verify=$?
    fi
    printf '%s guest=%s verify=%s\n' "$test_case" "$guest" "$verify" | tee -a "$xos_out/status.txt"
    if [ "$guest" -ne 0 ] || [ "$verify" -ne 0 ]; then failures=$((failures + 1)); fi
done
python3 tests/ssg_p3b_guest.py --image "$XOS_IMAGE" --supervisor "$xos_build/supervisor/supervisor.elf" \
    --browser "$xos_p3b/browser-test/browser.elf" --notes "$xos_p3b/notes/notes.elf" \
    --input tests/fixtures/ssg_browser/p2f.html --ordinary-sample --output "$xos_out/ordinary-sample" > "$xos_out/ordinary-sample.run.log" 2>&1
guest=$?
verify=99
if [ "$guest" -eq 0 ]; then
    python3 tests/ssg_p3b_ordinary_verify.py "$xos_out/ordinary-sample" > "$xos_out/ordinary-sample.verify.log" 2>&1
    verify=$?
fi
printf 'ordinary-sample guest=%s verify=%s\n' "$guest" "$verify" | tee -a "$xos_out/status.txt"
if [ "$guest" -ne 0 ] || [ "$verify" -ne 0 ]; then failures=$((failures + 1)); fi
printf 'compatibility_failures=%s\n' "$failures" | tee -a "$xos_out/status.txt"
[ "$failures" -eq 0 ]
