# SPDX-License-Identifier: Apache-2.0
"""Stage the previously qualified glibc C++ recipes for a fresh, signed C SDK."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / 'docs/reports/glibc_stock_fork_sdk_20261126'


def replace_once(value, old, new):
    if value.count(old) != 1:
        raise ValueError('frozen build recipe context changed: ' + old)
    return value.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/unified')
    args = parser.parse_args()
    output = args.output.resolve()
    relative = output.relative_to(ROOT)
    material = output / 'cxx/material'
    material.mkdir(parents=True, exist_ok=False)
    recipe = (RECIPE / 'build_glibc_cxx.sh').read_text()
    recipe = replace_once(recipe, '"$lib/libc.a" "$lib/libm.a" "$lib/libgcc.a"',
                          '"$lib/libc.a" "$lib/libm.a" "$lib/libxos_terminal.a" "$lib/libgcc.a"')
    anchor = 'export CC=/work/tools/ccc'
    prepare, separator, compile = recipe.partition(anchor)
    if not separator:
        raise ValueError('frozen build recipe has no compile phase')
    compile = replace_once(separator + compile, 'cd /work/std\n',
                           'cd /work/std\n'
                           "printf 'int main(void) { return 0; }\\n' >xos_link_test.c\n"
                           '"$CC" xos_link_test.c -o xos_link_test\n')
    prefix = ('#!/bin/bash\nset -euo pipefail\nsource=/work/upstream\n'
              'test -f /work/sdk/sysroot/usr/lib/libxos_terminal.a\n')
    (material / 'prepare.sh').write_text(prepare)
    (material / 'compile.sh').write_text(prefix + compile)
    (material / 'build-glibc-cxx.sh').write_text(prepare + compile)
    (material / 'build_unwinder.sh').write_bytes((RECIPE / 'build_unwinder.sh').read_bytes())

    assembly = replace_once((RECIPE / 'assemble.py').read_text(), "root / 'build/qualified'",
                            f'root / {str(relative)!r}')
    assembly = replace_once(assembly,
        "                'cxx_reconfigure_recipe_sha256': sha(cxx / 'material/reconfigure_cxx.sh'),",
        "                'cxx_prepare_recipe_sha256': sha(cxx / 'material/prepare.sh'),\n"
        "                'cxx_compile_recipe_sha256': sha(cxx / 'material/compile.sh'),")
    with (output / 'assemble.py').open('x') as script:
        script.write(assembly)


if __name__ == '__main__':
    main()
