#!/usr/bin/dash
# SPDX-License-Identifier: Apache-2.0
set -e
make -B -f /src/sl3/project.mk all
/out/sl3/c.elf
/out/sl3/cpp.elf
printf 'SL3_DASH_PROJECT_OK\n'
