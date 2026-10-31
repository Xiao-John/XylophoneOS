#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Measure the shared first-PageDown portion; this is only a partial comparison.
set -eu
if [ "$#" -ne 3 ]; then
    printf 'Usage: %s P3C_BUILD P3B_BUILD FRESH_OUTPUT\n' "$0" >&2
    exit 2
fi
: "${QEMU:?Set QEMU to the QEMU executable}"
: "${XOS_IMAGE:?Set XOS_IMAGE to the read-only XOS image}"
xos_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$xos_root"
xos_build=$1
xos_p3b=$2
xos_out=$3
python3 - "$xos_out" <<'PY'
from pathlib import Path
import sys
root = (Path.cwd() / 'build').resolve()
out = Path(sys.argv[1]).resolve()
if not out.is_relative_to(root) or out.exists():
    raise SystemExit('Choose a fresh output directory under build/')
out.mkdir(parents=True)
PY
python3 tests/ssg_p3b_guest.py --image "$XOS_IMAGE" --supervisor "$xos_p3b/aggregate-test/ssg-multi.elf" \
    --browser "$xos_p3b/browser-test/browser.elf" --notes "$xos_p3b/notes-test/notes.elf" \
    --input tests/fixtures/ssg_browser/p2f.html --case browser-scroll --output "$xos_out/p3b"
python3 tests/ssg_p3b_scroll_verify.py "$xos_out/p3b"
python3 tests/ssg_watch_guest.py --image "$XOS_IMAGE" --supervisor "$xos_build/supervisor-test/supervisor-test.elf" \
    --browser "$xos_p3b/browser-test/browser.elf" --notes "$xos_p3b/notes-test/notes.elf" \
    --browser-receipt "$xos_p3b/browser-test/browser.portable.receipt.json" \
    --input tests/fixtures/ssg_browser/p2f.html --case scroll --output "$xos_out/watch"
python3 tests/ssg_watch_verify.py "$xos_out/watch" --require-structured
python3 tests/ssg_watch_perf_compare.py --p3b "$xos_out/p3b" --watch "$xos_out/watch" --output "$xos_out/comparison.json"
