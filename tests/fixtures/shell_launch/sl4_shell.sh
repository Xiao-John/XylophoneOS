#!/usr/bin/dash
# SPDX-License-Identifier: Apache-2.0
set -e
PATH=/bin:/usr/bin
export PATH
sl4_probe query
renamed_probe query
sl4_probe chain 3
printf 'SL4_DASH_CHAIN_FOUR_OK\n'
sl4_probe reduce
sl4_probe inherit
sl4_probe arguments '' 'two words'
printf 'pipe-data' | sl4_probe copy > /tests/work/pipe.out
sl4_probe compare /tests/work/pipe.out pipe-data
cd /tests/work
SL4_VALUE='alpha beta'
export SL4_VALUE
/usr/bin/dash /tests/sl4_nested.sh
( sl4_probe query )
printf 'SL4_DASH_MATRIX_OK\n'
