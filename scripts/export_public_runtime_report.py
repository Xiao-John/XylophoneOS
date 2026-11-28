#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Export completed, source-bound public-runtime evidence without relabeling producers."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from ssg_public_paths import portable

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('guest-dir', 'runtime-build', 'gcc-shared-build', 'launcher-build',
                 'workspace', 'preview-prefix', 'preview-cellar', 'preview-temp', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--stage', type=Path, action='append', required=True)
    parser.add_argument('--source-rebuild', type=Path)
    parser.add_argument('--historical-guest-dir', type=Path, action='append', default=[])
    args = parser.parse_args()
    guest_path = args.guest_dir / 'report.json'
    guest = json.loads(guest_path.read_bytes())
    required = {'c-basic', 'c-policy', 'c-spawn', 'c-exec', 'cpp-xsh', 'cpp-dash', 'thread-xsh', 'thread-dash'}
    if (guest.get('status') != 'passed' or len(guest['checks']) != 8 * guest['rounds']
            or {row['name'] for row in guest['checks']} != required
            or any(row['status'] != 'passed' or row['resources_before'] != row['resources_after']
                   or row['resources_after'] != guest['baseline_resources'] for row in guest['checks'])):
        raise ValueError('the complete ordinary C/C++/shell guest matrix must pass before export')
    for name, expected in guest['inputs'].items():
        if sha(name) != expected:
            raise ValueError('qualified input changed before export: ' + name)
    raw = {'guest.json': guest_path, 'runtime_build.json': args.runtime_build / 'manifest.json',
           'shared_gcc_build.json': args.gcc_shared_build / 'manifest.json',
           'launcher_build.json': args.launcher_build / 'receipt.json'}
    for stage in args.stage:
        metadata = json.loads((stage / 'manifest.json').read_bytes())
        raw[metadata['name'] + '_build.json'] = stage / 'manifest.json'
    for name, path in raw.items():
        if name != 'guest.json' and guest['inputs'].get(str(path.resolve())) != sha(path):
            raise ValueError('build receipt was not bound by this guest run: ' + name)
    rebuilt = None
    if args.source_rebuild:
        rebuild_path = args.source_rebuild / 'report.json'
        rebuilt = json.loads(rebuild_path.read_bytes())
        libc_guest = '/usr/lib/xos/glibc_dynamic_v1/libc.so.0.1'
        if (rebuilt.get('status') != 'rebuilt_installed_bytes_identical'
                or rebuilt['installed_libc_sha256'] != guest['installed'][libc_guest]
                or sha(args.source_rebuild / 'libc.so.0.1') != guest['installed'][libc_guest]
                or rebuilt['inputs'].get(str((args.runtime_build / 'manifest.json').resolve()))
                   != sha(args.runtime_build / 'manifest.json')):
            raise ValueError('source-delta rebuild does not produce the actual qualified libc bytes')
        for name, expected in rebuilt['inputs'].items():
            if sha(name) != expected:
                raise ValueError('source-delta producer input changed: ' + name)
        raw['unsigned_mask_rebuild.json'] = rebuild_path
    historical = []
    for index, folder in enumerate(args.historical_guest_dir, 1):
        path = folder / 'report.json'
        data = json.loads(path.read_bytes())
        if data.get('status') not in ('passed', 'failed'):
            raise ValueError('historical guest report has no terminal outcome')
        for name, expected in data['inputs'].items():
            if sha(name) != expected:
                raise ValueError('historical guest input changed: ' + name)
        raw['historical_guest_' + str(index) + '.json'] = path
        historical.append((folder, data))
    out = args.output.resolve()
    out.relative_to(ROOT / 'docs/reports')
    out.mkdir(parents=True, exist_ok=False)
    mappings = [('XOS_ROOT', ROOT), ('XOS_WORKSPACE', args.workspace),
                ('XOS_PREVIEW2_CELLAR', args.preview_cellar),
                ('XOS_PREVIEW2_BREW', args.preview_prefix),
                ('XOS_PREVIEW2_TEMP', args.preview_temp)]
    for name, path in raw.items():
        content = json.loads(path.read_bytes())
        if name == 'guest.json' or name.startswith('historical_guest_'):
            # Only these fields are guest shell commands. Applying guest
            # roots to host source paths would change their replay meaning.
            for row in content['checks']:
                row['command'] = portable(row['command'],
                    [('XOS_GUEST_TESTS', '/tests'), ('XOS_GUEST_APPS', '/apps')], strict=True)
        content = portable(content, mappings, strict=True)
        (out / name).write_text(json.dumps(content, indent=2) + '\n')
    for stage in args.stage:
        name = json.loads((stage / 'manifest.json').read_bytes())['name']
        text = portable((stage / 'preflight.log').read_text(), mappings, strict=True)
        (out / (name + '_preflight.log')).write_text(text)
    serial = (args.guest_dir / 'public_runtime_serial.log').read_bytes()
    (out / 'serial.log.gz').write_bytes(gzip.compress(serial, mtime=0))
    for index, (folder, _) in enumerate(historical, 1):
        log = (folder / 'public_runtime_serial.log').read_bytes()
        (out / ('historical_serial_' + str(index) + '.log.gz')).write_bytes(gzip.compress(log, mtime=0))
    conversion = {'rule': 'known environment roots replaced by explicit replay templates; observations and source/artifact/tool hashes unchanged',
                  'raw_reports': {name: sha(path) for name, path in raw.items()},
                  'guest_command_roots': {'XOS_GUEST_TESTS': '/tests', 'XOS_GUEST_APPS': '/apps'},
                  'exporter_sha256': sha(__file__), 'leaf_bindings': 'manifest.json files'}
    (out / 'conversion.json').write_text(json.dumps(conversion, indent=2) + '\n')
    rows = '\n'.join('| ' + row['name'] + ' | ' + str(row['round']) + ' | '
                     + str(row['seconds']) + ' | passed |' for row in guest['checks'])
    rebuild_section = ''
    if rebuilt:
        rebuild_section = f'''## Later source correction and identical executed bytes

The unsigned CLOEXEC-mask correction was compiled from its new exact source
with the recorded GNU build command into an independent output. Its non-debug
relocatable object is byte-identical to the prior one. The actual GNU archive
was copied, only that member replaced, and all {rebuilt['unchanged_archive_members']}
other member payloads and the complete member order were checked unchanged.
The real GNU partial-link, stub cleanup, final shared-library link and debug
strip then produced an ELF byte-identical to the libc installed in this guest.
`unsigned_mask_rebuild.json` preserves the distinct old/new source identities,
actual commands and new artifacts. No old receipt or executable was edited.
This is an explicit new-source-to-existing-bytes proof; a different resulting
ELF would require restaging and another guest run.

'''
    history_section = ''
    if historical:
        history_section = "## Preserved earlier attempts\n\n"
        history_section += ("Earlier reports and serial logs retain their original source, SDK, artifact and outcome bindings. "
                            "They are not qualifications of this later build.\n\n")
        for index, (_, data) in enumerate(historical, 1):
            checks = data.get('checks', [])
            passed = sum(row.get('status') == 'passed' for row in checks)
            failed = ', '.join(row['name'] for row in checks if row.get('status') != 'passed') or 'none'
            history_section += (f"- Attempt {index}: `{data['status']}`, system `{data.get('native_build_id', 'unknown')}`, "
                                f"{passed}/{len(checks)} recorded cases passed; unsuccessful cases: {failed}.\n")
    (out / 'README.md').write_text(f'''# Public GNU runtime: ordinary entry qualification

The exact native system `{guest['native_build_id']}` passed all **{len(guest['checks'])}**
ordinary public-runtime cases. Every command returned the expected successful
completion and restored the same physical-page/process/completion baseline.
The production native controller used explicitly compiled approved generation
roots, ordinary SDK inspect/spawn/wait, transferred readonly file pins and the
actual GNU interpreter. The runtime was built by the public GNU `make lib`
path; no private `rtld-routines` substitution supplied this execution.

| Case | Round | Wall seconds | Result |
|---|---:|---:|---|
{rows}

The C cases cover constructors, TLS, relocation, environment, explicit runtime
dlopen/dlmopen/dlclose denial, inherited FD aliases/shared cursors, CLOEXEC,
ordinary posix_spawn with authenticated readiness, failed exec cancellation
that retains the old process, and successful same-PID image replacement.
The C++ cases exercise actual shared GNU libstdc++/libgcc/libm, a separately
linked C++ DSO, cross-DSO exceptions, RTTI, unwinding, TLS teardown, atexit,
std::thread move/join and isolated application/DSO thread-local state. C++ and
thread programs enter through both ordinary xsh and dash commands. The outer
dash is a separately bound static-libc baseline; it is used as a shell entry,
not represented as a build of the tested shared libc.

The sequential ELF-metadata parser preserves the 30-second absolute startup
budget. Each entry's wall time includes controller installation, any requested
activation, inspection, launch, native/GNU startup and final completion; it
is not a claim that these independent controller operations share one deadline.

`guest.json` binds the complete native/C SDK identities, immutable system and
runtime sources, producer receipts, application bytes, compiler/interpreter
inputs and actual commands. Inputs were checked before and after execution,
and again at export. Build receipts retain `built_not_run`; this separate
guest report records execution instead of modifying historical producers.
The flat root manifest covers all exported leaves and git authenticates it.
`conversion.json` preserves raw report identities and records mechanical
environment-path substitution. `${{XOS_WORKSPACE}}` is the explicitly selected
development workspace; `${{XOS_ROOT}}` is this checkout. The Preview2 prefix,
Cellar and temporary-root templates identify that pinned SDK environment.
Within the recorded guest shell commands, `${{XOS_GUEST_TESTS}}` means `/tests`
and `${{XOS_GUEST_APPS}}` means `/apps`; those templates are never applied to
host source paths or artifact identities. Serial output preserves guest paths.

{rebuild_section}
{history_section}
## Scope

Approval and activation remain bounded per-controller volatile state. This
matrix does not qualify durable global catalogs, power-loss recovery, online
library loading, cross-descendant revocation, dynamic fork-to-exec controller
migration, terminal-actor dynamic exec, or the dynamic-libc/DHCP combination.
The final R2 generation-transition evidence and static R1 SDK qualifications
are separate reports with their own exact source and artifact bindings.
''')
    files = {path.name: sha(path) for path in sorted(out.iterdir()) if path.is_file()}
    (out / 'manifest.json').write_text(json.dumps({'version': 1, 'files': files}, indent=2) + '\n')
    print('exported', len(files), 'bound public runtime evidence files')


if __name__ == '__main__':
    main()
