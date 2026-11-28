#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run from the matching source checkout inside the Preview 2 SDK environment.
set -euo pipefail

if (( $# > 1 )); then
    echo 'usage: replay.sh [system-directory]' >&2
    exit 2
fi
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.."
XOS_P0_SYSTEM=${1:-build/candidates/p0-final-20261128-r2/system}
export XOS_QMP_TRANSPORT=pipe
export ASAN_OPTIONS=detect_leaks=0

for suite in launch ipc deadline stdio; do
    for kind in fixture guest; do
        output="build/p0_root_candidate_${suite}_${kind}"
        if [[ -e "$output" || -L "$output" ]]; then
            echo "refusing an existing output: $output" >&2
            exit 1
        fi
    done
done

python3 scripts/build_launch_control_probe.py \
    --sdk "$XOS_P0_SYSTEM/sdk" --output build/p0_root_candidate_launch_fixture
python3 scripts/build_ipc_exec_probe.py \
    --sdk "$XOS_P0_SYSTEM/sdk" --output build/p0_root_candidate_ipc_fixture
python3 scripts/build_ipc_deadline_probe.py \
    --sdk "$XOS_P0_SYSTEM/sdk" --output build/p0_root_candidate_deadline_fixture
python3 scripts/build_static_stdio_probe.py \
    --system "$XOS_P0_SYSTEM" --system-source . \
    --output build/p0_root_candidate_stdio_fixture
python3 tests/launch_control_guest.py \
    --system "$XOS_P0_SYSTEM" --fixture build/p0_root_candidate_launch_fixture \
    --output build/p0_root_candidate_launch_guest --repeat 3
python3 tests/ipc_exec_guest.py \
    --system "$XOS_P0_SYSTEM" --fixture build/p0_root_candidate_ipc_fixture \
    --output build/p0_root_candidate_ipc_guest --repeat 3 --serial-only --suite lifecycle
python3 tests/ipc_exec_guest.py \
    --system "$XOS_P0_SYSTEM" --fixture build/p0_root_candidate_deadline_fixture \
    --output build/p0_root_candidate_deadline_guest --repeat 3 --serial-only --suite deadline
python3 tests/static_stdio_compat_guest.py \
    --system "$XOS_P0_SYSTEM" --system-source . \
    --fixture build/p0_root_candidate_stdio_fixture \
    --output build/p0_root_candidate_stdio_guest --repeat 3
