# SPDX-License-Identifier: Apache-2.0
"""Bind PX4-A design calling points to exact source bytes; not a guest test."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
KERNEL = {
    'src/kernel/core/memory.cpp': ['allocate_page', 'release_page'],
    'src/kernel/arch/x86_64/paging.cpp': ['map_page_in', 'unmap_page_in', 'query_page_in', 'copy_user_pages_in', 'create_address_space', 'destroy_address_space'],
    'src/kernel/arch/x86_64/tasks.cpp': ['user_range_ok', 'set_heap_break', 'pinned_range', 'sys_wait_word', 'prepare_fork', 'sys_process_exec_prepare', 'sys_process_exec_commit', 'sys_process_map', 'destroy_task'],
    'src/shared/include/xos/process_abi.hpp': ['process_user_begin', 'process_heap_begin', 'process_max_pages'],
    'src/shared/include/xos/thread_abi.hpp': ['thread_arena_begin'],
    'src/user/libc/newlib_syscalls.cpp': ['void* mmap', 'int munmap'],
    'src/user/loader/load.cpp': ['process_map', 'process_create', 'process_abort'],
    'src/user/loader/elf.cpp': ['if (kind != 1)', 'map_write', 'map_execute'],
    'src/boot/x86/kernel_loader.asm': ['cpu_requires_long_mode_nx_pae', 'LME + NXE'],
}
V8 = {
    'include/v8-platform.h': ['AllocatePages', 'SetPermissions', 'DecommitPages', 'RecommitPages', 'DiscardSystemPages'],
    'src/base/platform/platform-posix.cc': ['void* OS::Allocate(', 'void OS::Free(', 'bool OS::SetPermissions(', 'bool OS::RecommitPages(', 'bool OS::DecommitPages(', 'MAP_FIXED | MAP_ANONYMOUS'],
    'src/base/platform/platform.h': ['kReadWriteExecute', 'DecommitPages'],
    'src/sandbox/sandbox.h': ['(Ideally) 1 TB', '32 GB', 'partially-reserved', 'first four GB'],
    'src/common/globals.h': ['kMaximalCodeRangeSize', 'kMinimumCodeRangeSize'],
    'src/base/page-allocator.cc': ['PageAllocator::AllocatePages', 'PageAllocator::SetPermissions', 'PageAllocator::DecommitPages'],
}
SHA = 'bb294624702efbb17691b642333f06bf5108e600'


def record(base, path, needles):
    p = base / path
    data = p.read_bytes()
    lines = data.decode().splitlines()
    found = {s: [i for i, line in enumerate(lines, 1) if s in line] for s in needles}
    assert all(found.values()), (path, found)
    return {'path': path, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'calling_points': found}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--v8', type=Path, required=True)
    ap.add_argument('--extra', type=Path, required=True)
    ap.add_argument('--source-lock', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    lock = json.loads(a.source_lock.read_text())
    assert lock['v8']['sha'] == SHA
    expected = {r['path'][3:]: r['sha256'] for r in lock['files'] if r.get('status') == 'PASSED' and r['path'].startswith('v8/')}
    out = {'kind': 'SOURCE_AUDIT_ONLY', 'guest_status': 'NOT_RUN', 'kernel_base': subprocess.check_output(['git', 'rev-parse', 'origin/main'], cwd=ROOT, text=True).strip(), 'v8_sha': SHA, 'source_lock_sha256': hashlib.sha256(a.source_lock.read_bytes()).hexdigest(), 'kernel': [], 'v8': []}
    for p, needles in KERNEL.items():
        out['kernel'].append(record(ROOT, p, needles))
    for p, needles in V8.items():
        base = a.v8 if (a.v8 / p).exists() else a.extra
        r = record(base, p, needles)
        r['url'] = f'https://chromium.googlesource.com/v8/v8/+/{SHA}/{p}'
        if p in expected:
            assert r['sha256'] == expected[p], p
            r['phase1_hash_verified'] = True
        else:
            r['phase1_hash_verified'] = False
        out['v8'].append(r)
    out['additional_fetch'] = json.loads((a.extra / 'fetch.json').read_text())
    out['standards_fetch'] = [{'url': f'https://pubs.opengroup.org/onlinepubs/9799919799/functions/{n}.html', 'status': 'FAILED', 'error': 'web open returned 403 Forbidden'} for n in ['mmap', 'munmap', 'mprotect']]
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(out, indent=2) + '\n')


if __name__ == '__main__':
    main()
