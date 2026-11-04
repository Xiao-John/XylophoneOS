#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Run the affected single-source regressions against one P3B build.
# Set QEMU, XOS_IMAGE, XOS_DASH_ELF and the SDK/Qt receipt input paths.
set -u
if [ "$#" -ne 2 ]; then
    printf 'Usage: %s BUILD_DIR OUTPUT_PREFIX\n' "$0" >&2
    exit 2
fi
: "${QEMU:?Set QEMU to the QEMU executable}"
: "${XOS_IMAGE:?Set XOS_IMAGE to the read-only XOS image}"
: "${XOS_DASH_ELF:?Set XOS_DASH_ELF to the separately built dash executable}"
: "${XOS_SDK_PREFIX:?Set XOS_SDK_PREFIX to the SDK used by this build}"
: "${XOS_BUILD_DIR:?Set XOS_BUILD_DIR to the Qt build used by this build}"
: "${XOS_QT_SOURCE:?Set XOS_QT_SOURCE to the Qt source used by this build}"
xos_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$xos_root" || exit 2
xos_build=$1
xos_prefix=$2
python3 - "$xos_prefix" <<'PY' || exit 2
from pathlib import Path
import sys
root = (Path.cwd() / 'build').resolve()
prefix = Path(sys.argv[1]).resolve()
if not prefix.is_relative_to(root) or not prefix.parent.is_dir():
    raise SystemExit('Output prefix must be in an existing directory under build/')
if prefix.exists() or any(prefix.parent.glob(prefix.name + '-*')):
    raise SystemExit('Output prefix already has files; choose a fresh prefix')
PY
xos_session=$xos_build/session/session.elf
xos_consumer=$xos_build/consumer/ssg-consumer.elf
xos_consumer_test=$xos_build/consumer-test/ssg-consumer.elf
xos_notes=$xos_build/notes/notes.elf
xos_notes_test=$xos_build/notes-test/notes.elf
xos_browser=$xos_build/browser/browser.elf
xos_browser_test=$xos_build/browser-test/browser.elf
xos_receipt=$xos_build/browser-test/browser.portable.receipt.json
xos_input=tests/fixtures/ssg_browser/p2f.html
failures=0
run_step() {
    local label=$1 log=$2 rc
    shift 2
    "$@" > "$log" 2>&1
    rc=$?
    printf '%s=%s\n' "$label" "$rc"
    if [ "$rc" -ne 0 ]; then failures=$((failures + 1)); fi
}
run_browser() {
    local label=$1 guest=$2 browser=$3
    shift 3
    run_step "$label guest" "$xos_prefix-$label.log" python3 "tests/$guest" \
        --image "$XOS_IMAGE" --session "$xos_session" --browser "$browser" \
        --consumer "$xos_consumer" --input "$xos_input" --output "$xos_prefix-$label" "$@"
}
run_verifier() {
    local label=$1 verifier=$2
    shift 2
    run_step "$label $verifier" "$xos_prefix-$label-$verifier.log" \
        python3 "tests/$verifier" "$xos_prefix-$label" "$@"
}
run_browser pages-oracle ssg_browser_pages_probe.py "$xos_browser_test" --require-oracle --browser-receipt "$xos_receipt"
run_browser scroll-diff ssg_p2g4_guest.py "$xos_browser"
run_verifier scroll-diff ssg_p2g4_verify.py
run_browser recovery ssg_p2g5_guest.py "$xos_browser_test"
run_verifier recovery ssg_p2g5_verify.py
run_verifier recovery ssg_p2g6_oracle_verify.py --browser-receipt "$xos_receipt"
run_browser exhaust ssg_p2g6_exhaust_guest.py "$xos_browser"
run_verifier exhaust ssg_p2g6_exhaust_verify.py
run_browser reload ssg_p2g6_reload_guest.py "$xos_browser"
run_verifier reload ssg_p2g6_reload_verify.py
run_browser navigation ssg_p2g6_navigation_guest.py "$xos_browser_test" --link-hit --browser-receipt "$xos_receipt"
run_verifier navigation ssg_p2g6_navigation_verify.py
run_step notes-range "$xos_prefix-notes-range.log" python3 tests/ssg_text_range_guest.py \
    --image "$XOS_IMAGE" --session "$xos_session" --consumer "$xos_consumer" --notes "$xos_notes" --output "$xos_prefix-notes-range"
run_step notes-boundaries "$xos_prefix-notes-boundaries.log" python3 tests/ssg_range_boundaries_guest.py \
    --image "$XOS_IMAGE" --payload "$xos_build/boundaries/probe.elf" --output "$xos_prefix-notes-boundaries"
for test_case in edit no-edit revoke protect-document protect-ancestor; do
    run_step "notes-$test_case guest" "$xos_prefix-notes-$test_case.log" python3 tests/ssg_notes_live_edit_guest.py \
        --image "$XOS_IMAGE" --session "$xos_session" --consumer "$xos_consumer_test" --notes "$xos_notes_test" \
        --case "$test_case" --output "$xos_prefix-notes-$test_case"
    run_step "notes-$test_case independent" "$xos_prefix-notes-$test_case-verify.log" \
        python3 tests/ssg_notes_live_verify.py "$xos_prefix-notes-$test_case"
done
run_step notes-no-log "$xos_prefix-notes-no-log.log" python3 tests/ssg_notes_live_no_log_guest.py \
    --image "$XOS_IMAGE" --session "$xos_session" --consumer "$xos_consumer" --notes "$xos_notes" --output "$xos_prefix-notes-no-log"
run_step p1 "$xos_prefix-p1.log" python3 tests/ssg_ipc_guest.py \
    --image "$XOS_IMAGE" --session "$xos_session" --consumer "$xos_consumer" --notes "$xos_notes" \
    --browser "$xos_browser" --dash "$XOS_DASH_ELF" --output "$xos_prefix-p1"
printf 'regression_failures=%s\n' "$failures"
[ "$failures" -eq 0 ]
