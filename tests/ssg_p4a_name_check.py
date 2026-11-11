#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check new P4A-owned type/function and Python definition names for C30."""
import ast
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
cpp_files = (
    'src/user/apps/ssg_multi_session.cpp',
    'src/user/apps/ssg_subscriber.cpp',
    'src/user/ssg/pipe_event_sink.hpp',
    'src/user/ssg/subscriber_state.hpp',
    'src/user/ssg/subscription_wire.hpp',
    'tests/fixtures/qt6/ssg_p4a_state_test.cpp',
)
py_files = (
    'scripts/build_ssg_p4a.py', 'scripts/export_ssg_p4a_report.py',
    'scripts/prepare_ssg_p4a_toolchain.py', 'scripts/run_ssg_p4a_validation.py',
    'tests/ssg_p4a_guest.py', 'tests/ssg_p4a_host_test.py',
    'tests/ssg_p4a_resync_verify.py', 'tests/ssg_p4a_state_guest.py',
    'tests/ssg_p4a_verify.py', 'tests/ssg_p4a_name_check.py',
)
snake = re.compile(r'^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$')
type_decl = re.compile(r'\b(?:class|struct|enum\s+class)\s+([A-Za-z_][A-Za-z0-9_]*)')
function_def = re.compile(
    r'^\s*(?:static\s+)?(?:inline\s+)?[A-Za-z_][A-Za-z0-9_:<>*& ]*?\s+'
    r'([A-Za-z_][A-Za-z0-9_]*)\s*\([^;\n]*\)\s*(?:const\s*)?\{', re.M)


def main():
    failures = []
    checked = []
    for relative in cpp_files:
        path = root / relative
        text = path.read_text()
        if not any('SPDX-License-Identifier:' in line for line in text.splitlines()[:3]):
            failures.append(f'{relative}: missing SPDX header')
        names = set(type_decl.findall(text)) | set(function_def.findall(text))
        for name in sorted(names):
            if not snake.fullmatch(name):
                failures.append(f'{relative}: {name}')
        checked.append({'file': relative, 'definitions': sorted(names)})
    for relative in py_files:
        path = root / relative
        text = path.read_text()
        if not any('SPDX-License-Identifier:' in line for line in text.splitlines()[:3]):
            failures.append(f'{relative}: missing SPDX header')
        tree = ast.parse(text, filename=relative)
        names = [node.name for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names.extend(target.id for target in targets if isinstance(target, ast.Name))
        for name in names:
            if not snake.fullmatch(name) and not (name.startswith('__') and name.endswith('__')):
                failures.append(f'{relative}: {name}')
        checked.append({'file': relative, 'definitions': sorted(names)})
    report = {'status': 'FAIL' if failures else 'PASS', 'checked_files': checked,
              'failures': failures, 'rules': ['C30 snake_case for P4A-owned definitions',
                                               'SPDX header present on P4A code and test files']}
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
