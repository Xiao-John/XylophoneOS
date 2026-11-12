#!/usr/bin/dash
# SPDX-License-Identifier: Apache-2.0
set -e
../../bin/sl4_probe environment
sl4_probe arguments '' 'two words'
printf 'SL4_NESTED_DASH_OK\n'
