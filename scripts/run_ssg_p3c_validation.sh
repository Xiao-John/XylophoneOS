#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Run the synthetic two-provider watch cases on a matched image and build.
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
python3 tests/ssg_watch_contract_guest.py --image "$XOS_IMAGE" \
    --payload "$xos_build/contract-test/contract-test.elf" --output "$xos_out/contract" > "$xos_out/contract.log" 2>&1
status=$?
printf 'contract guest=%s\n' "$status" | tee -a "$xos_out/status.txt"
if [ "$status" -ne 0 ]; then failures=$((failures + 1)); fi
for test_case in baseline edit scroll reload revoke protect-document protect-ancestor browser-exit notes-exit notes-timeout stop cancel-inflight; do
    python3 tests/ssg_watch_guest.py --image "$XOS_IMAGE" \
        --supervisor "$xos_build/supervisor-test/supervisor-test.elf" \
        --browser "$xos_p3b/browser-test/browser.elf" --notes "$xos_p3b/notes-test/notes.elf" \
        --browser-receipt "$xos_p3b/browser-test/browser.portable.receipt.json" \
        --input tests/fixtures/ssg_browser/p2f.html --case "$test_case" --output "$xos_out/$test_case" > "$xos_out/$test_case.run.log" 2>&1
    guest=$?
    verify=99
    if [ "$guest" -eq 0 ]; then
        if [ "$test_case" = cancel-inflight ]; then
            python3 tests/ssg_watch_cancel_verify.py "$xos_out/$test_case" > "$xos_out/$test_case.verify.log" 2>&1
        elif [ "$test_case" = notes-timeout ]; then
            python3 tests/ssg_watch_timeout_verify.py "$xos_out/$test_case" > "$xos_out/$test_case.verify.log" 2>&1
        else
            python3 tests/ssg_watch_verify.py "$xos_out/$test_case" --require-structured > "$xos_out/$test_case.verify.log" 2>&1
        fi
        verify=$?
    fi
    printf '%s guest=%s verify=%s\n' "$test_case" "$guest" "$verify" | tee -a "$xos_out/status.txt"
    if [ "$guest" -ne 0 ] || [ "$verify" -ne 0 ]; then failures=$((failures + 1)); fi
done
python3 tests/ssg_watch_guest.py --image "$XOS_IMAGE" \
    --supervisor "$xos_build/supervisor/supervisor.elf" \
    --browser "$xos_p3b/browser/browser.elf" --notes "$xos_p3b/notes/notes.elf" \
    --browser-receipt "$xos_p3b/browser/browser.portable.receipt.json" \
    --input tests/fixtures/ssg_browser/p2f.html --ordinary --output "$xos_out/ordinary" > "$xos_out/ordinary.run.log" 2>&1
guest=$?
verify=99
if [ "$guest" -eq 0 ]; then
    python3 tests/ssg_watch_nondiagnostic_verify.py "$xos_out/ordinary" --require-structured > "$xos_out/ordinary.verify.log" 2>&1
    verify=$?
fi
printf 'ordinary guest=%s verify=%s\n' "$guest" "$verify" | tee -a "$xos_out/status.txt"
if [ "$guest" -ne 0 ] || [ "$verify" -ne 0 ]; then failures=$((failures + 1)); fi
printf 'validation_failures=%s\n' "$failures" | tee -a "$xos_out/status.txt"
[ "$failures" -eq 0 ]
