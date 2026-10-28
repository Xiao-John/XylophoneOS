#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay E15 preparation and the separate E16 raster/FreeType patch in a NEW tree."""
from pathlib import Path
import subprocess
import sys
here=Path(__file__).resolve().parent
if len(sys.argv)!=3:raise SystemExit('usage: prepare_gui_source.py LOCKED_ARCHIVE NEW_DIRECTORY')
subprocess.run([sys.executable,here/'prepare_source.py',*sys.argv[1:]],check=True)
subprocess.run(['patch','-p1','-i',str(here/'patches/0008-xos-gui-platform.patch')],cwd=Path(sys.argv[2]),check=True)
