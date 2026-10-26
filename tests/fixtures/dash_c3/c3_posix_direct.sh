#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
printf 'C3_DIRECT argc=%s arg1=<%s> arg2=<%s> name=<%s> env=<%s>\n' "$#" "$1" "$2" "$0" "$e"
value=$(printf 'captured\n\n')
read here <<'C3_DIRECT_BODY'
literal $NO_EXPAND
C3_DIRECT_BODY
printf 'C3_DIRECT substitution=<%s> here=<%s>\n' "$value" "$here"
v=child
e=child
export e
cd /tmp || exit 91
set -- replaced
printf 'C3_DIRECT child_cwd=%s\n' "$PWD"
exit 17
