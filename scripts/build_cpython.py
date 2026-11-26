# SPDX-License-Identifier: Apache-2.0
"""Build CPython with the stock XOS SDK or an explicit static glibc profile."""

import argparse
from pathlib import Path

from build_cpython_legacy import main as legacy_main


def main():
    selector = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    selector.add_argument('--glibc-profile', type=Path)
    selection, _ = selector.parse_known_args()
    if selection.glibc_profile is None:
        legacy_main()
    else:
        from build_cpython_glibc import main as glibc_main
        glibc_main()


if __name__ == '__main__':
    main()
