# SPDX-License-Identifier: Apache-2.0
PATH=/usr/bin:/bin:/
CC=/usr/bin/x86_64-elf-gcc
CXX=/usr/bin/x86_64-elf-g++
export PATH CC CXX

. /tests/helper.sh
classify_source /src/current.c || exit 70
printf 'parameter=%s\n' "${DASH_B_VALUE:-fallback}"

if "$CC" --sysroot=/sysroot -I/src -c /src/bad.c -o /out/bad.o; then
    printf 'unexpected_compile_success\n'
    exit 71
else
    printf 'expected_compile_failure=%s\n' "$?"
fi

cp /src/good.c /src/current.c || exit 72
compile_c_app /src/current.c /src/value.c -o /out/c_app.elf || exit 73
/out/c_app.elf || exit 74

classify_source /src/app.cpp || exit 75
"$CXX" -std=gnu++17 -static --sysroot=/sysroot /src/app.cpp -o /out/cpp_app.elf || exit 76
/out/cpp_app.elf || exit 77

mkdir -p /out/tool_test/nested || exit 78
cp /src/message.txt /out/tool_test/nested/copied.txt || exit 79
mv /out/tool_test/nested/copied.txt /out/tool_test/nested/moved.txt || exit 80
cat /out/tool_test/nested/moved.txt || exit 81
rm /out/tool_test/nested/moved.txt || exit 82
if test -e /out/tool_test/nested/moved.txt; then exit 83; fi
printf 'dash_b1=ok\n'
