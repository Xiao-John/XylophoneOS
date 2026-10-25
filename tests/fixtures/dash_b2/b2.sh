# SPDX-License-Identifier: Apache-2.0
set -e

printf 'alpha\n' > /out/log.txt
printf 'beta\n' >> /out/log.txt
cat < /out/log.txt > /out/copy.txt

/out/stdio_probe > /out/shared.txt 2>&1
printf 'order_two_start\n'
/out/stdio_probe 2>&1 > /out/split.txt
printf 'order_two_end\n'

printf 'inside_builtin\n' > /out/builtin.txt
printf 'restoration_marker\n'

if printf 'must_not_exist\n' > /missing/out.txt; then
    printf 'unexpected_redirection_success\n'
    exit 9
else
    printf 'expected_redirection_failure\n'
fi

printf 'log_begin\n'
cat /out/copy.txt
printf 'log_end\nshared_begin\n'
cat /out/shared.txt
printf 'shared_end\nsplit_begin\n'
cat /out/split.txt
printf 'split_end\nbuiltin_begin\n'
cat /out/builtin.txt
printf 'builtin_end\nb2=ok\n'
