#!/usr/bin/dash
# SPDX-License-Identifier: Apache-2.0
set -e
gmake -B -r -f /src/native/project.mk all
/out/native/c.elf
/out/native/cpp.elf
printf 'GLIBC_GNU_SEED_DASH_OK\n'
