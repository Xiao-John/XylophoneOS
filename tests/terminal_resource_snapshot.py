# SPDX-License-Identifier: Apache-2.0
"""Read-only QMP resource observations bound to one exact kernel image.

This is a test-side interpretation of private symbols, not a guest ABI or a
permission change. Samples preserve the complete bytes and QMP transcript.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time


SYMBOLS = {
    'free_pages': ('_ZN3xos12_GLOBAL__N_1L15free_page_countE', 4),
    'tasks': ('_ZN3xos4arch12_GLOBAL__N_1L10task_totalE', 4),
    'completion_records': ('_ZN3xos4arch12_GLOBAL__N_1L11completionsE', 16 * 80),
}
SOURCE_FILES = ('src/kernel/arch/x86_64/tasks.cpp', 'src/kernel/core/memory.cpp',
                'src/kernel/core/cpu_accounting.hpp', 'src/shared/include/xos/process_abi.hpp')


def _sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _loads(elf):
    if len(elf) < 64 or elf[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<HHI', elf, 16) != (2, 62, 1):
        raise ValueError('resource sampler requires static little-endian x86-64 ELF64')
    phoff = struct.unpack_from('<Q', elf, 32)[0]
    ehsize, phsize, count = struct.unpack_from('<HHH', elf, 52)
    if ehsize != 64 or phsize != 56 or not 1 <= count <= 32 or phoff < 64 or phoff + count * phsize > len(elf):
        raise ValueError('invalid kernel program-header geometry')
    result = []
    for index in range(count):
        kind, flags, offset, virtual, physical, files, memory, alignment = struct.unpack_from('<II6Q', elf, phoff + index * phsize)
        if kind in (2, 3):
            raise ValueError('dynamic kernel is outside resource-sampler scope')
        if kind != 1:
            continue
        if (files > memory or offset + files > len(elf) or virtual + memory >= 1 << 64 or
                physical + memory >= 1 << 64 or virtual != physical or flags & 3 == 3 or
                alignment != 4096 or virtual % alignment != offset % alignment):
            raise ValueError('invalid or nonidentity kernel PT_LOAD')
        result.append({'virtual': virtual, 'physical': physical, 'file_bytes': files,
                       'memory_bytes': memory, 'flags': flags, 'offset': offset})
    if sorted(item['flags'] for item in result) != [4, 5, 6]:
        raise ValueError('expected exactly RX, R and RW kernel PT_LOAD segments')
    return result


def resolve_kernel_layout(elf, nm_text):
    """Validate exact symbol names/sizes against file and physical geometry."""
    loads = _loads(elf)
    symbols = {}
    for label, (name, size) in SYMBOLS.items():
        rows = [line.split() for line in nm_text.splitlines() if line.split() and line.split()[-1] == name]
        if len(rows) != 1 or len(rows[0]) != 4:
            raise ValueError('missing or duplicate exact kernel resource symbol: ' + name)
        address, measured_size, kind, found = rows[0]
        address, measured_size = int(address, 16), int(measured_size, 16)
        if found != name or kind not in ('b', 'B') or measured_size != size or address % 4:
            raise ValueError('kernel resource symbol type/size/alignment changed: ' + name)
        containing = [load for load in loads if load['virtual'] <= address and
                      address + size <= load['virtual'] + load['memory_bytes']]
        if (len(containing) != 1 or containing[0]['flags'] != 6 or
                address < containing[0]['virtual'] + containing[0]['file_bytes']):
            raise ValueError('resource symbol is not fully inside the bound RW BSS: ' + name)
        load = containing[0]
        symbols[label] = {'name': name, 'virtual': address,
                          'physical': load['physical'] + address - load['virtual'], 'bytes': size}
    regions = sorted((item['physical'], item['physical'] + item['bytes']) for item in symbols.values())
    if any(left[1] > right[0] for left, right in zip(regions, regions[1:])):
        raise ValueError('resource symbols overlap')
    return {'loads': loads, 'symbols': symbols, 'completion_capacity': 16,
            'completion_record_bytes': 80, 'completion_used_byte_offset': 0}


def _verify_inputs(binding):
    core = {key: value for key, value in binding.items() if key != 'binding_sha256'}
    if _identity(core) != binding.get('binding_sha256'):
        raise ValueError('resource binding metadata changed')
    for path, expected in binding['inputs'].items():
        if _sha(path) != expected:
            raise ValueError('bound resource-sampler input changed: ' + path)


def bind_kernel_resources(system, source_root, output, *, nm_path=None):
    system, source_root, output = (Path(path).resolve() for path in (system, source_root, output))
    manifest_path = system / 'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    inputs = {str(manifest_path): _sha(manifest_path), str(Path(__file__).resolve()): _sha(__file__)}
    for name in ('kernel.elf', 'xos-install.iso'):
        path = system / name
        expected = manifest['artifacts'][name]
        if path.stat().st_size != expected['bytes'] or _sha(path) != expected['sha256']:
            raise ValueError('kernel/boot image differs from system manifest: ' + name)
        inputs[str(path)] = expected['sha256']
    for name in SOURCE_FILES:
        path = source_root / name
        expected = manifest['sources'][name]
        if _sha(path) != expected:
            raise ValueError('resource-layout source differs from system manifest: ' + name)
        inputs[str(path)] = expected
    tasks = (source_root / SOURCE_FILES[0]).read_text()
    memory = (source_root / SOURCE_FILES[1]).read_text()
    expected_record = 'struct completion_record { bool used; bool ready; bool published; u64 parent; process_status status; cpu_totals cpu; };'
    if (expected_record not in tasks or 'completion_record completions[16];' not in tasks or
            'u32 task_total;' not in tasks or 'u32 free_page_count;' not in memory):
        raise ValueError('private kernel resource layout declarations changed')
    selected = nm_path or shutil.which('x86_64-elf-nm') or shutil.which('nm')
    if not selected:
        raise ValueError('nm is required to bind resource symbols')
    nm = Path(selected).resolve(strict=True)
    inputs[str(nm)] = _sha(nm)
    command = [str(nm), '-S', '--defined-only', str(system / 'kernel.elf')]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=15)
    nm_text = result.stdout.decode('utf-8', errors='strict')
    layout = resolve_kernel_layout((system / 'kernel.elf').read_bytes(), nm_text)
    version = subprocess.check_output([str(nm), '--version'], text=True, timeout=15).splitlines()[0]
    output.mkdir(parents=True, exist_ok=False)
    nm_log, nm_error = output / 'kernel_nm.txt', output / 'kernel_nm_stderr.txt'
    nm_log.write_bytes(result.stdout)
    nm_error.write_bytes(result.stderr)
    inputs[str(nm_log)] = _sha(nm_log)
    inputs[str(nm_error)] = _sha(nm_error)
    binding = {'version': 1, 'scope': 'test-only external read of private bound kernel resource symbols',
               'system_build_id': manifest['build_id'], 'system_manifest': str(manifest_path),
               'kernel_elf': str(system / 'kernel.elf'), 'boot_image': str(system / 'xos-install.iso'),
               'nm': {'path': str(nm), 'version': version, 'command': command},
               'layout': layout, 'inputs': inputs}
    binding['binding_sha256'] = _identity(binding)
    (output / 'binding.json').write_text(json.dumps(binding, indent=2) + '\n')
    return binding


def decode_resource_bytes(raw):
    if set(raw) != set(SYMBOLS) or any(len(raw[name]) != SYMBOLS[name][1] for name in SYMBOLS):
        raise ValueError('incomplete or wrongly sized raw kernel resource bytes')
    records = raw['completion_records']
    entries = []
    for index in range(16):
        offset = index * 80
        used, ready, published = records[offset:offset + 3]
        if max(used, ready, published) > 1:
            raise ValueError('invalid kernel completion bool byte')
        entries.append({'slot': index, 'used': used, 'ready': ready, 'published': published,
                        'parent': struct.unpack_from('<Q', records, offset + 8)[0],
                        'pid': struct.unpack_from('<Q', records, offset + 24)[0]})
    values = {'free_pages': struct.unpack('<I', raw['free_pages'])[0],
              'tasks': struct.unpack('<I', raw['tasks'])[0],
              'completions': sum(entry['used'] for entry in entries)}
    if not 0 < values['free_pages'] < 131072 or not 0 < values['tasks'] <= 8:
        raise ValueError('impossible resource counters for this 512-MiB uniprocessor profile')
    return values, entries


def sample_kernel_resources(guest, binding, output, label):
    if re.fullmatch(r'[A-Za-z0-9_-]+', label) is None:
        raise ValueError('noncanonical resource sample label')
    _verify_inputs(binding)
    command = guest.command
    if ('-cdrom' not in command or Path(command[command.index('-cdrom') + 1]).resolve() != Path(binding['boot_image']) or
            '-smp' not in command or command[command.index('-smp') + 1] != '1' or
            '-m' not in command or command[command.index('-m') + 1] != '512M'):
        raise ValueError('QMP guest is not this bound boot image and machine scope')
    directory = Path(output).resolve() / label
    directory.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'label': label, 'binding_sha256': binding['binding_sha256'],
              'system_build_id': binding['system_build_id'], 'qemu_command': list(command),
              'raw_files': {}, 'raw_hex': {},
              'qmp_commands': [], 'started_host_monotonic_ns': time.monotonic_ns()}
    resume_required = False

    def qmp(execute, arguments=None):
        row = {'execute': execute}
        if arguments is not None:
            row['arguments'] = arguments
        report['qmp_commands'].append(row)
        try:
            row['response'] = guest.qmp(execute, arguments)
            return row['response']
        except BaseException as error:
            row['error'] = str(error)
            raise

    try:
        if qmp('query-status').get('running') is not True:
            raise ValueError('refuse to change the state of an already paused guest')
        resume_required = True
        qmp('stop')
        if qmp('query-status').get('running') is not False:
            raise ValueError('QEMU did not stop before resource reads')
        report['paused_host_monotonic_ns'] = time.monotonic_ns()
        raw = {}
        for name, symbol in binding['layout']['symbols'].items():
            path = directory / (name + '.bin')
            qmp('pmemsave', {'val': symbol['physical'], 'size': symbol['bytes'], 'filename': str(path)})
            raw[name] = path.read_bytes()
            if len(raw[name]) != symbol['bytes']:
                raise ValueError('short QMP physical memory observation: ' + name)
            report['raw_files'][str(path)] = _sha(path)
            report['raw_hex'][name] = raw[name].hex()
        report['values'], report['completion_entries'] = decode_resource_bytes(raw)
        report['status'] = 'sampled'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        try:
            if resume_required:
                qmp('cont')
                if qmp('query-status').get('running') is not True:
                    raise ValueError('QEMU did not resume after resource observation')
                report['resumed_host_monotonic_ns'] = time.monotonic_ns()
        except BaseException as error:
            report['status'] = 'failed'
            report['resume_error'] = str(error)
            raise
        finally:
            report['finished_host_monotonic_ns'] = time.monotonic_ns()
            (directory / 'sample.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def verify_kernel_resource_pair(samples, *, native):
    if len(samples) != 2:
        raise AssertionError('exactly two kernel resource samples are required')
    first, second = samples
    if (any(sample.get('status') != 'sampled' for sample in samples) or
            first['binding_sha256'] != second['binding_sha256'] or first['label'] == second['label'] or
            first['finished_host_monotonic_ns'] >= second['started_host_monotonic_ns'] or
            first['raw_files'].keys() & second['raw_files'].keys()):
        raise AssertionError('kernel resource observations are incomplete or not separate ordered samples')
    for sample in samples:
        commands = sample['qmp_commands']
        if ([row['execute'] for row in commands] !=
                ['query-status', 'stop', 'query-status', 'pmemsave', 'pmemsave',
                 'pmemsave', 'cont', 'query-status'] or
                any('error' in row for row in commands) or
                commands[0]['response'].get('running') is not True or
                commands[2]['response'].get('running') is not False or
                commands[7]['response'].get('running') is not True or
                not sample['started_host_monotonic_ns'] < sample['paused_host_monotonic_ns'] <
                sample['resumed_host_monotonic_ns'] < sample['finished_host_monotonic_ns']):
            raise AssertionError('resource bytes were not captured in a complete stop/read/resume interval')
        for path, expected in sample['raw_files'].items():
            if _sha(path) != expected:
                raise AssertionError('raw kernel resource observation changed')
        values, entries = decode_resource_bytes({name: bytes.fromhex(value) for name, value in sample['raw_hex'].items()})
        if values != sample['values'] or entries != sample['completion_entries']:
            raise AssertionError('decoded kernel resource report differs from retained raw bytes')
        # Every serialized byte must also be backed by a unique retained file.
        expected_digests = sorted(hashlib.sha256(bytes.fromhex(value)).hexdigest() for value in sample['raw_hex'].values())
        if expected_digests != sorted(sample['raw_files'].values()):
            raise AssertionError('kernel resource hex is not the retained pmemsave output')
    values = first['values']
    if (values != second['values'] or values['tasks'] != 2 or values['completions'] != 0 or
            native.get('free_pages') != values['free_pages'] or native.get('tasks') != values['tasks']):
        raise AssertionError('global kernel resources are not stable or differ from native observer state')
    return dict(values)
