# SPDX-License-Identifier: Apache-2.0
"""Decode guest compiler outcomes and -v search/child traces without executing tools."""
import argparse
import json
from pathlib import Path
import re

HOST_PREFIXES = ('/Users/', '/opt/homebrew/', '/Applications/', '/Library/Developer/', '/private/')


def diagnose(output, command=''):
    text = output.decode(errors='replace') if isinstance(output, bytes) else output
    # The serial echo is not compiler evidence.
    lines = text.splitlines()
    if lines and (lines[0].startswith(('exec-file ', 'exec-driver ', 'spawn-file ')) or lines[0] == command):
        lines = lines[1:]
    actual = '\n'.join(lines)
    waits = re.findall(r'\[wait\] pid=(\d+) kind=(\w+)(?: code=(-?\d+))?', actual)
    result = {'command': command, 'outcome': 'missing_result', 'exit_code': None,
              'stage': 'unknown', 'child_commands': [], 'include_search_paths': [],
              'host_path_leaks': []}
    if waits:
        pid, kind, code = waits[-1]
        result.update(pid=int(pid), outcome=kind, exit_code=int(code) if code else None)
    in_search = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'#include [<"].*[>"] search starts here:', stripped):
            in_search = True
            continue
        if in_search:
            if stripped == 'End of search list.':
                in_search = False
            elif stripped.startswith('/'):
                result['include_search_paths'].append(stripped)
        # GCC can invoke the assembler by its basename through posix_spawnp.
        # Do not inspect "Configured with:" host provenance as runtime searches.
        if re.match(r'^\s+/\S+(?:\s|$)', line) and not in_search:
            if re.search(r'/(?:cc1(?:plus)?|collect2|(?:x86_64-elf-)?(?:as|ld))(?:\s|$)', stripped):
                result['child_commands'].append(stripped)
        elif not in_search and re.match(r'^\s+(?:x86_64-elf-)?(?:as|ld)\s', line):
            result['child_commands'].append(stripped)
    for value in result['include_search_paths'] + result['child_commands']:
        if any(prefix in value for prefix in HOST_PREFIXES):
            result['host_path_leaks'].append(value)
    lower = actual.lower()
    if result['outcome'] in ('faulted', 'killed'):
        result['stage'] = 'runtime_' + result['outcome']
    elif 'elf: rejected reason=' in lower:
        result['stage'] = 'elf_validation'
    elif 'exec-file: error=' in lower or '[loader] error' in lower:
        result['stage'] = 'loader'
    elif 'operation not permitted' in lower or 'permission denied' in lower:
        result['stage'] = 'subprocess_authority_or_access'
    elif 'out of memory' in lower or 'cannot allocate memory' in lower:
        result['stage'] = 'memory'
    elif 'cannot execute' in lower or 'cannot find cc1' in lower or 'cannot find as' in lower:
        result['stage'] = 'subprocess_lookup'
    elif 'undefined reference' in lower or 'ld returned' in lower or 'cannot find -l' in lower:
        result['stage'] = 'link'
    elif 'no such file or directory' in lower:
        result['stage'] = 'source_or_include_lookup'
    elif re.search(r'(?:fatal )?error:', lower):
        result['stage'] = 'compile'
    elif result['outcome'] == 'exited' and result['exit_code'] == 0:
        result['stage'] = 'completed'
    result['classification_is_hint'] = True
    return result


def guest_command(line, drivers=()):
    """Turn a tool invocation into an explicit supervisor command."""
    if line.startswith(('exec-file ', 'exec-driver ', 'spawn-file ')):
        return line
    executable = line.split(' ', 1)[0]
    return ('exec-driver ' if executable in drivers else 'exec-file ') + line


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('serial_log', type=Path)
    parser.add_argument('--command', default='')
    args = parser.parse_args()
    print(json.dumps(diagnose(args.serial_log.read_bytes(), args.command), indent=2))


if __name__ == '__main__':
    main()
