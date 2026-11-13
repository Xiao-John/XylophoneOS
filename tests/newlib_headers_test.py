# SPDX-License-Identifier: Apache-2.0
"""Compile and run atomics and tgmath against the regenerated SDK headers."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "scripts"))
from newlib_patches import apply_patches


def main():
    with tempfile.TemporaryDirectory(prefix="xos_newlib_headers_") as temporary:
        work = Path(temporary)
        include = work / "include"
        shutil.copytree(repo_root / "src/third_party/newlib/x86_64-elf/include", include)
        apply_patches(include, headers=True)
        apply_patches(include, headers=True)
        source = work / "probe.c"
        source.write_text(r'''
#include <stddef.h>
#include <stdint.h>
#include <stdatomic.h>
#include <tgmath.h>
#define TYPE(expression, type) _Static_assert(__builtin_types_compatible_p(__typeof__(expression), type), #expression)
TYPE(sqrt(4.0f), float);
TYPE(sqrt(4.0), double);
TYPE(sqrt(4.0L), long double);
TYPE(sqrt(4), double);
TYPE(pow(2.0f, 3.0f), float);
TYPE(pow(2.0f, 3), double);
TYPE(pow(2.0f, 3.0L), long double);
TYPE(sqrt(4.0f + 0.0f * I), float _Complex);
TYPE(sqrt(4.0L + 0.0L * I), long double _Complex);
TYPE(ceil(2.0f), float);
TYPE(ceil(2.0L), long double);
atomic_int value = ATOMIC_VAR_INIT(2);
atomic_flag flag = ATOMIC_FLAG_INIT;
int main(void) {
    atomic_init(&value, 7);
    if (atomic_fetch_add(&value, 3) != 7 || atomic_load(&value) != 10) return 1;
    int expected = 10;
    if (!atomic_compare_exchange_strong(&value, &expected, 12)) return 2;
    if (atomic_flag_test_and_set(&flag) || !atomic_flag_test_and_set(&flag)) return 3;
    atomic_flag_clear(&flag);
    if (atomic_flag_test_and_set(&flag)) return 4;
    float number = 4.0f;
    if (sqrt(number++) != 2.0f || number != 5.0f) return 5;
    if (sqrt(4.0L) != 2.0L || pow(2.0f, 3.0L) != 8.0L) return 6;
    return 0;
}
''')
        binary = work / "probe"
        subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-O0",
                        "-Wall", "-Wextra", "-Werror", "-isystem", str(include),
                        str(source), "-lm", "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print("PASS regenerated newlib headers: atomic initialization/operations, math types and single evaluation")


if __name__ == "__main__":
    main()
