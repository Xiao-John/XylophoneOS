#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Template identified host command paths while leaving guest payloads untouched."""
import collections
import hashlib
import json
import re

from verify_evidence_index import no_duplicates

temp_root = re.compile(r'(?<![A-Za-z0-9_./-])(?:/private/var/fol' r'ders/|/private/tm' r'p/|/var/fol' r'ders/|/tm' r'p/)[^/\s,;"\'\\]+')
workspace_root = re.compile(r'(?<![A-Za-z0-9_./-])/work' r'space/[^/\s,;"\'\\]+')
homebrew_root = re.compile(r'(?<![A-Za-z0-9_./-])/opt/homebrew(?=/|$)')
relative_qemu = '../runtime/qemu-prefix/opt/qemu/bin/qemu-system-x86_64'
legacy_qemu = '<home>/Documents/ChatGPT/os/runtime/qemu-prefix/opt/qemu/bin/qemu-system-x86_64'
host_logs = {
    'docs/reports/modern_apps_20261029/build/localpilot-wheel-attempt2.log.gz',
    'docs/reports/modern_apps_20261029/build/python-build.log.gz',
    'docs/reports/modern_apps_20261029/build/sqlite-compile-attempt1.log.gz',
    'docs/reports/qt_e15_qualified_20261028/sbase_wrong_assembler_failure.log.gz',
    'docs/reports/qt_e16_qualified_20261028/system_regressions/threading_cpp_smoke.runner.log.gz',
}
host_build_json = {
    'src/ports/gcc/e08_5_abi_build_report.json',
    'docs/reports/daily_utilities_20261028/system_manifest.json.gz',
}
host_environment_files = {
    'docs/reports/fb0_20261029/service_system_manifest.json.gz',
    'docs/reports/fb0_20261029/system_manifest.json.gz',
    'docs/reports/fb12_20261029/attempts/mixed_old_build_log.gz',
    'docs/reports/fb12_20261029/system_manifest.json.gz',
    'docs/reports/fb12_dash_20261029/system_manifest.json.gz',
}
host_documents = {
    'docs/reports/pr_8_review.md',
    'docs/work_log/0063_input_edit_design.md',
    'docs/work_log/0064_input_edit_first_stage.md',
    'docs/work_log/0075_ncursesw_preliminary_gaps.md',
    'docs/work_log/0076_utf8_link_probe.md',
    'docs/work_log/0077_full_remote_integration.md',
    'docs/work_log/0080_fb0_fault_bundle.md',
    'docs/work_log/0082_network_device_abi_claim.md',
    'docs/work_log/0096_browser_review_fixes.md',
    'docs/work_log/0099_probe_branch_reconciliation.md',
    'docs/work_log/0144_webengine_port_plan_and_c31.md',
}
host_temp_bytes = re.compile(rb'(?<![A-Za-z0-9_./-])(?:/private/var/fol' rb'ders/|/private/tm' rb'p/|/var/fol' rb'ders/|/tm' rb'p/)[^/\s,;"\'\\]+')
host_document_temp = re.compile(rb'(?<![A-Za-z0-9_./-])(?:/private/var/fol' rb'ders/|/private/tm' rb'p/|/var/fol' rb'ders/|/tm' rb'p/)[^/\s,;"\'`\\)\]{}<>]+')
host_workspace_bytes = re.compile(rb'(?<![A-Za-z0-9_./-])/work' rb'space/[^/\s,;"\'\\]+')
host_runtime_bytes = re.compile(rb'(?<![A-Za-z0-9_./-])/opt/codex/run' rb'times/[^/\s,;"\'\\]+')


def template_qemu_json(data):
    """Return (bytes, variables, skipped roots) without changing guest fields.

    A complete JSON string token is replaced only when every occurrence of
    that token is inside an explicitly identified host command. Identical values
    used elsewhere remain unchanged for review.
    """
    try:
        obj = json.loads(data, object_pairs_hook=no_duplicates)
    except (ValueError, UnicodeError):
        return data, {}, []
    strings = []

    def collect(value):
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)

    def walk(value, scope=''):
        if isinstance(value, dict):
            for key, item in value.items():
                qemu_list = (key == 'command' and isinstance(item, list) and item and
                             isinstance(item[0], str) and 'qemu-system' in item[0])
                reference_command = scope == 'host_reference' and key == 'command'
                compiler_commands = scope == 'threaded_probe' and key == 'commands'
                if key in ('qemu_command', 'qemu_commands') or qemu_list or reference_command or compiler_commands:
                    collect(item)
                else:
                    walk(item, key if key in ('host_reference', 'threaded_probe') else scope)
        elif isinstance(value, list):
            for item in value:
                walk(item, scope)

    walk(obj)
    counts = collections.Counter(strings)
    variables = {}
    skipped = []
    for value in sorted(counts, key=len, reverse=True):
        local_variables = {}

        def replace(kind):
            def apply(match):
                raw = match.group().encode('utf-8')
                name = ('XOS_' + kind if kind == 'HOMEBREW' else
                        'XOS_' + kind + '_' + hashlib.sha256(raw).hexdigest()[:12].upper())
                local_variables[name] = kind.lower()
                return '${' + name + '}'
            return apply

        updated = value
        for kind, pattern in (('HOST_TEMP', temp_root), ('WORKSPACE', workspace_root), ('HOMEBREW', homebrew_root)):
            updated = pattern.sub(replace(kind), updated)
        for token, kind in ((relative_qemu, 'QEMU'), (legacy_qemu, 'QEMU'), ('<repo>', 'ROOT')):
            if token in updated:
                updated = updated.replace(token, '${XOS_' + kind + '}')
                local_variables['XOS_' + kind] = kind.lower()
        if updated == value:
            continue
        encodings = {json.dumps(value, ensure_ascii=True).encode(), json.dumps(value, ensure_ascii=False).encode()}
        occurrences = sum(data.count(token) for token in encodings)
        if occurrences != counts[value]:
            skipped.append(hashlib.sha256(value.encode()).hexdigest())
            continue
        for token in encodings:
            if token in data:
                # The source's escaping style is retained for non-ASCII text.
                ascii_style = token == json.dumps(value, ensure_ascii=True).encode()
                data = data.replace(token, json.dumps(updated, ensure_ascii=ascii_style).encode())
        variables.update(local_variables)
    return data, variables, skipped


def template_reviewed_host_data(data, name):
    """Template only explicitly reviewed host build logs and command fields."""
    variables = {}
    if name in host_logs:
        cache = {}

        def replace(match):
            raw = match.group()
            if raw not in cache:
                token = 'XOS_BUILD_TEMP_' + hashlib.sha256(raw).hexdigest()[:12].upper()
                cache[raw] = ('${' + token + '}').encode()
                variables[token] = 'reviewed host build temp root'
            return cache[raw]
        data = host_temp_bytes.sub(replace, data)
    if name in host_documents:
        def replace_document_temp(match):
            raw = match.group()
            token = 'XOS_DOC_TEMP_' + hashlib.sha256(raw).hexdigest()[:12].upper()
            variables[token] = 'reviewed historical host temp root'
            return ('${' + token + '}').encode()
        data = host_document_temp.sub(replace_document_temp, data)
    if name in host_build_json and b'/opt/homebrew' in data:
        data = data.replace(b'/opt/homebrew', b'${XOS_HOMEBREW}')
        variables['XOS_HOMEBREW'] = 'reviewed host toolchain root'
    if name in host_environment_files:
        for kind, pattern in (('WORKSPACE', host_workspace_bytes), ('RUNTIME', host_runtime_bytes)):
            def replace_environment(match):
                raw = match.group()
                token = 'XOS_' + kind + '_' + hashlib.sha256(raw).hexdigest()[:12].upper()
                variables[token] = 'reviewed host environment root'
                return ('${' + token + '}').encode()
            data = pattern.sub(replace_environment, data)
    if name == 'docs/reports/threading_20261025/threading_compile_report.json' and b'<repo>' in data:
        data = data.replace(b'<repo>', b'${XOS_ROOT}')
        variables['XOS_ROOT'] = 'reviewed host source root'
    if name == 'docs/reports/dash_c3_20261026/regression_summary.json':
        obj = json.loads(data, object_pairs_hook=no_duplicates)
        value = '../runtime/xos-1024-images.tar.gz'
        count = 0

        def walk(item):
            nonlocal count
            if isinstance(item, dict):
                for key, child in item.items():
                    if key == 'command' and isinstance(child, list):
                        count += sum(1 for part in child if part == value)
                    else:
                        walk(child)
            elif isinstance(item, list):
                for child in item:
                    walk(child)
        walk(obj)
        encoded = json.dumps(value).encode()
        if count and data.count(encoded) == count:
            data = data.replace(encoded, b'"${XOS_INPUT_ARCHIVE}"')
            variables['XOS_INPUT_ARCHIVE'] = 'reviewed host input archive'
    if name == 'docs/reports/qt_e17_qualified_20261029/attempts/save-cases-1/report.json':
        obj = json.loads(data, object_pairs_hook=no_duplicates)
        error = obj.get('error') if isinstance(obj, dict) else None
        if isinstance(error, str) and error.startswith('Command ') and 'work_disk_host' in error:
            local_variables = {}

            def replace_error(match):
                raw = match.group().encode()
                token = 'XOS_BUILD_TEMP_' + hashlib.sha256(raw).hexdigest()[:12].upper()
                local_variables[token] = 'reviewed host command temp root'
                return '${' + token + '}'
            updated = temp_root.sub(replace_error, error)
            encoded = json.dumps(error, ensure_ascii=True).encode()
            if updated != error and data.count(encoded) == 1:
                data = data.replace(encoded, json.dumps(updated, ensure_ascii=True).encode())
                variables.update(local_variables)
    return data, variables
