#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""SL3: receipt-bound native C/C++ Make projects through ordinary xsh and dash."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repo_root / 'scripts'), str(repo_root / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from shell_launch_support import (add_arguments, bind_native_inputs, boot_guest,
                                  install_files, run_case, sha, write_report)

fixture_root = repo_root / 'tests/fixtures/shell_launch'


def prepare_project_disk(args, bound, folder, report):
    disk = folder / 'work.img'
    create_fat32(disk, 2048)
    created = set()
    install_files(disk, args.seed_root, bound['seed'], created)
    install_files(disk, args.sysroot_root, bound['sysroot'], created)
    for directory in ('/bin', '/usr', '/usr/bin', '/src', '/src/sl3', '/out', '/out/sl3', '/tmp', '/tests', '/tests/work'):
        if directory not in created:
            transfer(disk, 'mkdir', directory)
            created.add(directory)
    transfer(disk, 'import', '/usr/bin/make', bound['make'])
    transfer(disk, 'import', '/usr/bin/dash', bound['dash'])
    names = ('project.h', 'project_value.c', 'project_c.c', 'project_cpp.cpp', 'project_cpp_value.cpp', 'link_error.c')
    report['fixtures'] = {}
    for name in names:
        source = fixture_root / name
        transfer(disk, 'import', '/src/sl3/' + name, source)
        report['fixtures'][name] = sha(source)
    makefile = folder / 'project.mk'
    text = (fixture_root / 'project.mk').read_text()
    for variable, tool in (('cc', 'gcc'), ('cxx', 'g++'), ('ar', 'ar')):
        text = text.replace('@' + variable + '@', bound['tools'][tool]['guest_path'])
    makefile.write_text(text)
    transfer(disk, 'import', '/src/sl3/project.mk', makefile)
    report['fixtures']['project.mk'] = sha(makefile)
    transfer(disk, 'import', '/tests/build_project.sh', fixture_root / 'build_project.sh')
    report['fixtures']['build_project.sh'] = sha(fixture_root / 'build_project.sh')
    return disk


def run_project(guest, report):
    run_case(guest, report, 'native_c_cpp_make', 'xsh', 'make -B -f /src/sl3/project.mk all', timeout=600)
    run_case(guest, report, 'native_c_program', 'xsh', '/out/sl3/c.elf', [b'SL3_C_OK'])
    run_case(guest, report, 'native_cpp_program', 'xsh', '/out/sl3/cpp.elf', [b'SL3_CPP_OK'])
    run_case(guest, report, 'native_c_cpp_make_and_programs', 'dash', 'dash /tests/build_project.sh',
             [b'SL3_C_OK', b'SL3_CPP_OK', b'SL3_DASH_PROJECT_OK'], timeout=600)


def export_project(disk, folder, report):
    report['outputs'] = {}
    for name in ('c.elf', 'cpp.elf', 'libvalue.a'):
        path = folder / name
        transfer(disk, 'export', '/out/sl3/' + name, path)
        report['outputs'][name] = {'sha256': sha(path), 'bytes': path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    parser.add_argument('--report', type=Path, default=repo_root / 'build/shell_launch_sl3_make/report.json')
    args = parser.parse_args()
    report = {'status': 'not_run', 'guest_execution': 'not_run', 'checks': [], 'gate': 'SL3 C/C++ Make'}
    guest = None
    code = 1
    try:
        bound = bind_native_inputs(args, report)
        if args.preflight_only:
            report['status'] = 'preflight_passed'
            code = 0
        else:
            with tempfile.TemporaryDirectory(prefix='xos_sl3_native_') as temporary:
                folder = Path(temporary)
                disk = prepare_project_disk(args, bound, folder, report)
                guest = Guest(args.system / 'xos-install.iso', 'sl3_native', work_disk=disk, iso=True)
                report['qemu_command'] = guest.command
                report['guest_execution'] = 'started'
                boot_guest(guest)
                run_project(guest, report)
                guest.close()
                (args.report.parent / 'serial.log').parent.mkdir(parents=True, exist_ok=True)
                (args.report.parent / 'serial.log').write_bytes(guest.output)
                guest = None
                # Export only after QEMU releases the disk.
                export_project(disk, folder, report)
                report['status'] = report['guest_execution'] = 'passed'
                code = 0
    except FileNotFoundError as error:
        report['status'] = 'not_run' if report['guest_execution'] == 'not_run' else 'failed'
        report['error'] = str(error)
        code = 2 if report['status'] == 'not_run' else 1
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
    finally:
        if guest is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            (args.report.parent / 'serial.log').write_bytes(guest.output)
            guest.close()
        write_report(args.report, report)
    print(report['status'].upper(), 'SL3 C/C++ Make:', len(report['checks']), 'guest checks')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
