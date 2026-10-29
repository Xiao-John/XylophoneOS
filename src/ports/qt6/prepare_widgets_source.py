#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare a fresh E17 tree from the verified 6.8.3 archive and E15/E16 patches."""
from pathlib import Path
import subprocess
import sys
here = Path(__file__).resolve().parent
if len(sys.argv) != 3:
    raise SystemExit('usage: prepare_widgets_source.py LOCKED_ARCHIVE NEW_DIRECTORY')
subprocess.run([sys.executable, here/'prepare_gui_source.py', *sys.argv[1:]], check=True)
