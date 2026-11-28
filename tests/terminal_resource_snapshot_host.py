# SPDX-License-Identifier: Apache-2.0
"""Exercise the exact ELF resource parser and failure-safe QMP sampler.

The ELF and its source/artifact manifest are real build inputs. QMP transport is
simulated here; the terminal C/D guest phases qualify the actual observations.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct

import terminal_resource_snapshot as snapshot


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reject(call, error=ValueError):
    try:
        call()
    except error:
        return
    raise AssertionError('expected rejection: ' + error.__name__)


def raw_values(*, pages=129000, tasks=2, used=()):
    records = bytearray(1280)
    for index in used:
        records[index * 80] = 1
        struct.pack_into('<Q', records, index * 80 + 8, 7)
        struct.pack_into('<Q', records, index * 80 + 24, index + 8)
    return {'free_pages': struct.pack('<I', pages), 'tasks': struct.pack('<I', tasks),
            'completion_records': bytes(records)}


class fake_guest:
    def __init__(self, binding, raw=None, *, failure=None, running=True):
        self.command = ['test-qemu', '-cdrom', binding['boot_image'], '-smp', '1', '-m', '512M']
        self.running = running
        self.failure = failure
        self.calls = []
        self.raw = raw or raw_values()
        self.by_address = {value['physical']: name for name, value in binding['layout']['symbols'].items()}

    def qmp(self, execute, arguments=None):
        self.calls.append(execute)
        if execute == 'query-status':
            return {'running': self.running, 'status': 'running' if self.running else 'paused'}
        if execute == 'stop':
            self.running = False
            if self.failure == 'stop':
                raise RuntimeError('lost stop reply after stopping')
        elif execute == 'cont':
            if self.failure == 'cont':
                raise RuntimeError('resume rejected')
            self.running = True
        elif execute == 'pmemsave':
            assert not self.running
            if self.failure == 'pmemsave':
                raise RuntimeError('physical read failed')
            name = self.by_address[arguments['val']]
            data = self.raw[name]
            assert arguments['size'] == len(data)
            if self.failure == 'short':
                data = data[:-1]
            Path(arguments['filename']).write_bytes(data)
        else:
            raise AssertionError('unexpected QMP action')
        return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'scope': 'actual kernel ELF parser; simulated QMP transport',
              'guest': 'not_run_by_this_runner', 'checks': [],
              'sources': {str(path.relative_to(ROOT)): digest(path) for path in
                          (Path(__file__).resolve(), Path(snapshot.__file__).resolve())}}

    def check(name, action):
        action()
        report['checks'].append({'name': name, 'status': 'passed'})
        print('PASS', name, flush=True)

    try:
        binding = snapshot.bind_kernel_resources(args.system, ROOT, output / 'binding')
        report['binding'] = binding
        elf = Path(binding['kernel_elf']).read_bytes()
        nm_text = (output / 'binding/kernel_nm.txt').read_text()
        completion_name = snapshot.SYMBOLS['completion_records'][0]
        completion_line = next(line for line in nm_text.splitlines() if line.split()[-1] == completion_name)
        address, size, kind, name = completion_line.split()

        def change_elf(offset, format, value):
            altered = bytearray(elf)
            struct.pack_into(format, altered, offset, value)
            return bytes(altered)

        def inspect(data=elf, symbols=nm_text):
            return snapshot.resolve_kernel_layout(data, symbols)

        def exact_layout():
            layout = inspect()
            assert layout == binding['layout']
            assert layout['symbols']['completion_records']['name'] == completion_name
            assert layout['completion_capacity'] == 16 and layout['completion_record_bytes'] == 80

        check('actual_elf_exact_symbols_and_rw_bss', exact_layout)
        check('unrelated_gpu_completion_symbol_is_ignored', lambda: inspect(symbols=nm_text +
              '\n0000000000000000 0000000000000008 b _ZN3xos10virtio_gpu12_GLOBAL__N_1L11completionsE\n'))
        check('missing_exact_symbol_rejected', lambda: reject(lambda: inspect(symbols=nm_text.replace(completion_line, ''))))
        check('duplicate_exact_symbol_rejected', lambda: reject(lambda: inspect(symbols=nm_text + completion_line + '\n')))
        check('wrong_completion_stride_rejected', lambda: reject(lambda: inspect(symbols=nm_text.replace(
              completion_line, f'{address} 00000000000004f0 {kind} {name}'))))
        check('wrong_symbol_storage_type_rejected', lambda: reject(lambda: inspect(symbols=nm_text.replace(
              completion_line, f'{address} {size} t {name}'))))
        rw = next(item for item in binding['layout']['loads'] if item['flags'] == 6)
        check('file_backed_symbol_rejected', lambda: reject(lambda: inspect(symbols=nm_text.replace(
              completion_line, f"{rw['virtual']:016x} {size} {kind} {name}"))))
        check('partially_outside_bss_rejected', lambda: reject(lambda: inspect(symbols=nm_text.replace(
              completion_line, f"{rw['virtual'] + rw['memory_bytes'] - 4:016x} {size} {kind} {name}"))))
        phoff = struct.unpack_from('<Q', elf, 32)[0]
        check('nonidentity_physical_mapping_rejected', lambda: reject(lambda: inspect(change_elf(
              phoff + 24, '<Q', struct.unpack_from('<Q', elf, phoff + 24)[0] + 4096))))
        check('writable_executable_load_rejected', lambda: reject(lambda: inspect(change_elf(phoff + 4, '<I', 7))))
        check('truncated_elf_rejected', lambda: reject(lambda: inspect(elf[:80])))
        check('wrong_elf_machine_rejected', lambda: reject(lambda: inspect(change_elf(18, '<H', 183))))

        def count_used():
            raw = raw_values(used=(0, 15))
            records = bytearray(raw['completion_records'])
            records[80 + 1:80 + 3] = b'\1\1'  # unused slot with stale diagnostics
            raw['completion_records'] = bytes(records)
            values, entries = snapshot.decode_resource_bytes(raw)
            assert values == {'free_pages': 129000, 'tasks': 2, 'completions': 2}
            assert entries[0]['pid'] == 8 and entries[15]['pid'] == 23

        check('count_all_used_slots_not_ready_or_published', count_used)
        invalid_bool = raw_values()
        invalid_bool['completion_records'] = b'\2' + invalid_bool['completion_records'][1:]
        check('invalid_completion_bool_rejected', lambda: reject(lambda: snapshot.decode_resource_bytes(invalid_bool)))
        short = raw_values()
        short['completion_records'] = short['completion_records'][:-1]
        check('short_raw_snapshot_rejected', lambda: reject(lambda: snapshot.decode_resource_bytes(short)))

        def sampled(label, raw=None):
            guest = fake_guest(binding, raw)
            value = snapshot.sample_kernel_resources(guest, binding, output / 'samples', label)
            assert guest.running and value['status'] == 'sampled'
            assert guest.calls == ['query-status', 'stop', 'query-status', 'pmemsave', 'pmemsave',
                                   'pmemsave', 'cont', 'query-status']
            return value

        good = [sampled('good_first'), sampled('good_second')]
        native = {'free_pages': 129000, 'tasks': 2}
        check('separate_samples_keep_raw_and_resume', lambda: snapshot.verify_kernel_resource_pair(good, native=native))

        def failed_sample(label, failure, error, *, initially_running=True):
            guest = fake_guest(binding, failure=failure, running=initially_running)
            reject(lambda: snapshot.sample_kernel_resources(guest, binding, output / 'samples', label), error)
            saved = json.loads((output / 'samples' / label / 'sample.json').read_bytes())
            assert saved['status'] == 'failed'
            if failure == 'cont':
                assert not guest.running and 'resume_error' in saved
            elif initially_running:
                assert guest.running and guest.calls[-2:] == ['cont', 'query-status']
            else:
                assert not guest.running and guest.calls == ['query-status']

        check('already_paused_guest_unchanged', lambda: failed_sample('paused', None, ValueError, initially_running=False))
        check('lost_stop_reply_restores_running_state', lambda: failed_sample('lost_stop', 'stop', RuntimeError))
        check('failed_read_restores_running_state', lambda: failed_sample('read_error', 'pmemsave', RuntimeError))
        check('short_read_restores_running_state', lambda: failed_sample('short_read', 'short', ValueError))
        check('failed_resume_is_retained_and_raised', lambda: failed_sample('resume_error', 'cont', RuntimeError))

        def wrong_image():
            guest = fake_guest(binding)
            guest.command[2] = str(output / 'other.iso')
            reject(lambda: snapshot.sample_kernel_resources(guest, binding, output / 'samples', 'wrong_image'))
            assert not guest.calls

        check('different_guest_image_rejected_before_qmp', wrong_image)

        def changed_bound_input():
            path = output / 'bound_sentinel'; path.write_bytes(b'before')
            changed = copy.deepcopy(binding)
            changed['inputs'][str(path)] = digest(path)
            changed['binding_sha256'] = snapshot._identity({key: value for key, value in changed.items() if key != 'binding_sha256'})
            path.write_bytes(b'after')
            guest = fake_guest(changed)
            reject(lambda: snapshot.sample_kernel_resources(guest, changed, output / 'samples', 'changed_input'))
            assert not guest.calls

        check('changed_bound_input_rejected_before_qmp', changed_bound_input)
        check('outstanding_completion_blocks_pair', lambda: reject(lambda: snapshot.verify_kernel_resource_pair(
              [sampled('used_first', raw_values(used=(15,))), sampled('used_second', raw_values(used=(15,)))], native=native), AssertionError))
        check('unstable_pages_block_pair', lambda: reject(lambda: snapshot.verify_kernel_resource_pair(
              [good[0], sampled('different_pages', raw_values(pages=129001))], native=native), AssertionError))
        check('native_global_mismatch_blocks_pair', lambda: reject(lambda: snapshot.verify_kernel_resource_pair(
              good, native={'free_pages': 129001, 'tasks': 2}), AssertionError))
        check('same_observation_cannot_count_twice', lambda: reject(lambda: snapshot.verify_kernel_resource_pair(
              [good[0], good[0]], native=native), AssertionError))
        check('reversed_observations_rejected', lambda: reject(lambda: snapshot.verify_kernel_resource_pair(
              list(reversed(good)), native=native), AssertionError))

        def changed_raw():
            pair = [sampled('raw_first'), sampled('raw_second')]
            Path(next(iter(pair[1]['raw_files']))).write_bytes(b'changed')
            reject(lambda: snapshot.verify_kernel_resource_pair(pair, native=native), AssertionError)

        check('tampered_retained_raw_rejected', changed_raw)

        def changed_report():
            pair = copy.deepcopy(good)
            pair[1]['raw_hex']['tasks'] = struct.pack('<I', 3).hex()
            reject(lambda: snapshot.verify_kernel_resource_pair(pair, native=native), AssertionError)

        check('report_hex_must_match_decoded_values', changed_report)

        def changed_qmp():
            pair = copy.deepcopy(good)
            pair[1]['qmp_commands'][2]['response']['running'] = True
            reject(lambda: snapshot.verify_kernel_resource_pair(pair, native=native), AssertionError)

        check('missing_pause_in_transcript_rejected', changed_qmp)
        assert all(digest(ROOT / name) == value for name, value in report['sources'].items())
        snapshot._verify_inputs(binding)
        report['status'] = 'passed'
        print('PASS', len(report['checks']), 'terminal resource snapshot host checks', flush=True)
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
