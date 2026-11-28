#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the generic IPC deadline probe with the recorded native worker profile."""
import argparse
from pathlib import Path
from build_ipc_exec_probe import INPUTS as COMMON_INPUTS, build_probe

INPUTS = ('tests/fixtures/ipc_deadline/ipc_deadline_probe.cpp', *COMMON_INPUTS[1:],
          'scripts/build_ipc_deadline_probe.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build_probe(args.sdk, args.output, source=INPUTS[0],
                extra_inputs=('scripts/build_ipc_deadline_probe.py',), binary_name='ipc_deadline_probe.elf')


if __name__ == '__main__':
    main()
