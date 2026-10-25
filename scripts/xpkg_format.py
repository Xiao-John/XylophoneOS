# SPDX-License-Identifier: Apache-2.0
"""XPK v1: bounded, deterministic ustar packages. No installation or code execution."""
import hashlib
import io
import json
import re
import struct
import tarfile
import tempfile
from pathlib import Path

MAX_MANIFEST = 1 << 20
MAX_MEMBERS = 8192
MAX_FILE = 64 << 20
MAX_PAYLOAD = 256 << 20
MAX_ARCHIVE = MAX_PAYLOAD + MAX_MANIFEST + (MAX_MEMBERS + 2) * 1024 + 10240
HEX = re.compile(r'[0-9a-f]{64}\Z')
IDENTIFIER = re.compile(r'[a-z][a-z0-9_]*(?:[.-][a-z0-9_]+)*\Z')
DEFAULT_PROFILE = Path(__file__).resolve().parents[1] / 'config/package/xos_x86_64_static_single_v1.json'


class PackageError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PackageError(message)


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def strict_json(data):
    require(len(data) <= MAX_MANIFEST, 'JSON exceeds 1 MiB')
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'duplicate JSON key: ' + key)
            out[key] = value
        return out
    def walk(value, depth=0):
        require(depth <= 8, 'JSON nesting exceeds 8')
        if isinstance(value, dict):
            for key, item in value.items():
                key.encode('utf-8', 'strict')
                walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1)
        elif isinstance(value, str):
            value.encode('utf-8', 'strict')
        elif isinstance(value, float):
            raise PackageError('floating point is not allowed in metadata')
    try:
        result = json.loads(data.decode('utf-8', 'strict'), object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(PackageError('invalid JSON number')))
        walk(result)
        return result
    except (UnicodeError, RecursionError, ValueError) as error:
        raise PackageError('invalid UTF-8 JSON: ' + str(error)) from error


def load_json(path):
    with Path(path).open('rb') as stream:
        return strict_json(stream.read(MAX_MANIFEST + 1))


def fields(value, required, optional=()):
    require(type(value) is dict, 'expected object')
    require(set(required) <= value.keys(), 'missing fields: ' + ', '.join(set(required) - value.keys()))
    require(value.keys() <= set(required) | set(optional), 'unknown fields: ' + ', '.join(value.keys() - set(required) - set(optional)))


def text(value, label):
    require(type(value) is str and 0 < len(value) <= 1024 and '\x00' not in value, 'invalid ' + label)
    return value


def identifier(value):
    require(type(value) is str and len(value) <= 80 and IDENTIFIER.fullmatch(value), 'invalid identifier')
    return value


def path_name(value, managed=True):
    require(type(value) is str and 0 < len(value.encode('utf-8')) <= 255, 'invalid path length')
    parts = value.split('/')
    for part in parts:
        require(part not in ('', '.', '..') and len(part) <= 100, 'invalid path component')
        require(re.fullmatch(r'[A-Za-z0-9_.+-]+', part) is not None, 'unsupported path characters or short-name alias')
        require(not part.endswith(('.', ' ')), 'trailing dot/space')
        require(not (part.upper().startswith('XOS') and part.upper().endswith('.TMP')), 'reserved recovery name')
    if managed:
        archive_name = 'payload/' + value
        require(len(archive_name) <= 100 or any(c == '/' and i <= 155 and len(archive_name) - i - 1 <= 100 for i, c in enumerate(archive_name)), 'path cannot be represented by ustar name/prefix')
        require(len(parts) >= 3 and parts[0] == 'usr' and parts[1] in ('bin', 'lib', 'share'), 'destination outside managed /usr roots')
        require(not (parts[1] == 'bin' and len(parts) != 3), '/usr/bin requires direct file names')
    return value


def confined(root, relative):
    path_name(relative, managed=False)
    root = Path(root).resolve(strict=True)
    path = root
    for part in relative.split('/'):
        path = path / part
        require(not path.is_symlink(), 'symlink source rejected: ' + relative)
    require(path.is_file(), 'missing regular source: ' + relative)
    require(path.resolve().is_relative_to(root), 'source escapes project')
    return path


def validate_manifest(value):
    fields(value, ('format_version', 'id', 'upstream_version', 'revision', 'target_profile',
                   'required_features', 'runtime_dependencies', 'files', 'licenses', 'build_receipt', 'source'))
    require(type(value['format_version']) is int and value['format_version'] == 1, 'unsupported XPK version')
    identifier(value['id']); identifier(value['target_profile'])
    text(value['upstream_version'], 'version'); text(value['source'], 'source provenance')
    require(type(value['revision']) is int and 0 <= value['revision'] < (1 << 31), 'invalid revision')
    features = value['required_features']
    require(type(features) is list and len(features) <= 64, 'invalid features')
    for feature in features:
        identifier(feature)
    require(len(features) == len(set(features)), 'duplicate feature')
    deps = value['runtime_dependencies']
    require(type(deps) is list and len(deps) <= 128, 'invalid runtime dependencies')
    dep_ids = set()
    for dep in deps:
        fields(dep, ('id', 'upstream_version', 'revision', 'sha256'))
        identifier(dep['id']); text(dep['upstream_version'], 'dependency version')
        require(type(dep['revision']) is int and 0 <= dep['revision'] < (1 << 31), 'invalid dependency revision')
        require(type(dep['sha256']) is str and HEX.fullmatch(dep['sha256']), 'invalid dependency hash')
        require(dep['id'] not in dep_ids and dep['id'] != value['id'], 'duplicate/self dependency')
        dep_ids.add(dep['id'])
    entries = value['files']
    require(type(entries) is list and 0 < len(entries) <= MAX_MEMBERS, 'invalid member count')
    names, total = {}, 0
    for entry in entries:
        fields(entry, ('path', 'type', 'size', 'sha256', 'role'))
        name = path_name(entry['path'])
        require(entry['type'] == 'file', 'P0 payload supports regular files only')
        require(entry['role'] in ('executable', 'data'), 'invalid payload role')
        require(type(entry['size']) is int and 0 <= entry['size'] <= MAX_FILE, 'invalid file size')
        require(type(entry['sha256']) is str and HEX.fullmatch(entry['sha256']), 'invalid file hash')
        folded = name.lower()
        require(folded not in names, 'duplicate/case-folded destination')
        names[folded] = entry
        total += entry['size']
    require(total <= MAX_PAYLOAD, 'payload exceeds 256 MiB')
    for name in names:
        parts = name.split('/')
        for i in range(1, len(parts)):
            require('/'.join(parts[:i]) not in names, 'file/directory collision')
    licenses = value['licenses']
    require(type(licenses) is list and 0 < len(licenses) <= MAX_MEMBERS, 'license materials required')
    require(len(licenses) == len(set(licenses)), 'duplicate license path')
    for name in licenses:
        path_name(name)
        require(name.lower() in names and names[name.lower()]['path'] == name, 'license not in payload')
        require(names[name.lower()]['role'] == 'data', 'license cannot be executable')
    receipt = value['build_receipt']
    fields(receipt, ('path', 'sha256'))
    path_name(receipt['path'])
    require(receipt['path'].lower() in names, 'build receipt not in payload')
    actual = names[receipt['path'].lower()]
    require(actual['path'] == receipt['path'] and actual['sha256'] == receipt['sha256'] and actual['role'] == 'data', 'receipt hash/path mismatch')
    return value


def check_profile(manifest, profile):
    require(profile['id'] == manifest['target_profile'], 'target profile mismatch')
    require(set(manifest['required_features']) <= set(profile['features']), 'required feature unavailable')


def inspect_elf(path):
    """Advisory ELF/layout check; not runtime authorization or an ABI proof."""
    borrowed = hasattr(path, 'read')
    stream = path if borrowed else Path(path).open('rb')
    try:
        size = stream.seek(0, 2)
        stream.seek(0)
        header = stream.read(64)
        require(len(header) == 64 and header[:7] == b'\x7fELF\x02\x01\x01', 'not ELF64 little-endian v1')
        kind, machine, version, entry, phoff = struct.unpack_from('<HHIQQ', header, 16)
        flags, ehsize, phsize, count = struct.unpack_from('<IHHH', header, 48)
        require(kind == 2 and machine == 62 and version == 1 and header[7] in (0, 3) and header[8] == 0 and flags == 0, 'unsupported ELF target/type')
        require(ehsize == 64 and phsize == 56 and 0 < count <= 32 and phoff >= 64 and phoff + count * 56 <= size, 'invalid program headers')
        stream.seek(phoff)
        headers = stream.read(count * 56)
        require(len(headers) == count * 56, 'truncated program headers')
    finally:
        if not borrowed:
            stream.close()
    tls_template, load_files = None, []
    loads, entry_ok, tls_seen, pages = [], False, False, 36
    image_end = 0x7ffdb000
    for i in range(count):
        typ, access, offset, address, _, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', headers, i * 56)
        if typ == 7:
            if filesz == memsz == 0:
                continue
            require(not tls_seen and access in (4, 6), 'invalid TLS segment')
            tls_seen = True
            tls_template = (offset, address, filesz)
            require(filesz <= memsz <= 0x100000 and offset + filesz <= size and 0x40000000 <= address < image_end and address + memsz <= image_end, 'invalid TLS bounds')
            align = align or 1
            require(align <= 65536 and align & (align - 1) == 0 and address % align == 0 and offset % align == 0, 'invalid TLS alignment')
            continue
        if typ != 1:
            require(typ in (0, 4, 6, 0x6474e552) or (typ == 0x6474e551 and access & 1 == 0), 'dynamic/unsupported ELF segment')
            continue
        if filesz == memsz == 0:
            continue
        require(filesz <= memsz and offset + filesz <= size, 'invalid LOAD file bounds')
        require(access in (4, 5, 6) and 0x40000000 <= address < image_end and address + memsz <= image_end, 'invalid LOAD permissions/address')
        require(align in (0, 1) or (align & (align - 1) == 0 and address % align == offset % align), 'invalid LOAD alignment')
        first, last = address & ~4095, (address + memsz + 4095) & ~4095
        require(last <= 0x5fe00000 or first >= 0x70000000, 'LOAD overlaps static TLS/heap arena')
        require(address % 4096 == offset % 4096, 'LOAD page congruence mismatch')
        require(not any(first < b and a < last for a, b in loads), 'overlapping LOAD pages')
        load_files.append((offset, address, filesz))
        loads.append((first, last)); pages += (last - first) // 4096
        entry_ok |= bool(access & 1 and address <= entry < address + filesz)
    if tls_template and tls_template[2]:
        off, addr, length = tls_template
        require(any(off >= o and off + length <= o + n and addr >= a and addr - a == off - o for o, a, n in load_files), 'TLS template outside LOAD bytes')
    require(0 < len(loads) <= 8 and entry_ok and pages <= 65536, 'invalid entry/LOAD count/page budget')
    return {'machine': 'x86_64', 'format': 'static_elf64', 'load_segments': len(loads), 'load_and_main_stack_pages': pages, 'static_tls': tls_seen}


def _number(raw):
    require(raw[:1] < b'\x80', 'base-256 tar integer unsupported')
    raw = raw.rstrip(b'\0 ').lstrip(b' ')
    require(not raw or all(c in b'01234567' for c in raw), 'invalid tar octal number')
    return int(raw or b'0', 8)


def _tar_name(raw):
    end = raw.find(b'\0')
    if end >= 0:
        require(not any(raw[end:]), 'garbage after tar string terminator')
        raw = raw[:end]
    try:
        return raw.decode('ascii')
    except UnicodeError as error:
        raise PackageError('non-ASCII tar path') from error


def verify_package(path, profile=None, expected_sha256=None, sink=None):
    """Verify exact bytes, with optional private callback; never extract via tarfile."""
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'package must be a regular non-symlink file')
    with path.open('rb') as stream:
        identity = (stream.seek(0, 2),)
        require(identity[0] <= MAX_ARCHIVE and identity[0] % 512 == 0, 'archive size/alignment invalid')
        stream.seek(0)
        package_hash = hashlib.sha256()
        def read(size):
            value = stream.read(size); package_hash.update(value)
            require(len(value) == size, 'truncated archive')
            return value
        manifest, expected, seen, index = None, {}, set(), 0
        while True:
            block = read(512)
            if not any(block):
                require(read(512) == bytes(512), 'missing two tar end blocks')
                while True:
                    tail = stream.read(65536)
                    if not tail:
                        break
                    package_hash.update(tail)
                    require(not any(tail), 'nonzero trailing archive data')
                break
            require(index <= MAX_MEMBERS, 'too many archive members')
            require(block[257:263] == b'ustar\0' and block[263:265] == b'00', 'only POSIX ustar is supported')
            require(_number(block[148:156]) == sum(block[:148]) + 8 * 32 + sum(block[156:]), 'tar checksum mismatch')
            require(block[156:157] in (b'0', b'\0') and not any(block[157:257]), 'only regular files; no links/extensions')
            require(not any(block[500:512]), 'nonzero tar header padding')
            name, prefix = _tar_name(block[:100]), _tar_name(block[345:500])
            name = prefix + '/' + name if prefix else name
            length = _number(block[124:136])
            if index == 0:
                require(name == 'manifest.json' and length <= MAX_MANIFEST, 'manifest must be first and bounded')
                manifest = validate_manifest(strict_json(read(length)))
                if profile is not None:
                    check_profile(manifest, profile)
                expected = {'payload/' + item['path']: item for item in manifest['files']}
            else:
                require(name in expected and name not in seen, 'extra/duplicate archive member: ' + name)
                item = expected[name]
                require(length == item['size'], 'member length mismatch: ' + name)
                digest, remaining = hashlib.sha256(), length
                # Disk-backed temporary stream bounds memory even for a 64 MiB executable.
                with tempfile.TemporaryFile() as executable:
                    if sink:
                        sink('begin', item, b'')
                    while remaining:
                        chunk = read(min(65536, remaining)); remaining -= len(chunk); digest.update(chunk)
                        if item['role'] == 'executable':
                            executable.write(chunk)
                        if sink:
                            sink('data', item, chunk)
                    require(digest.hexdigest() == item['sha256'], 'member hash mismatch: ' + name)
                    if item['role'] == 'executable':
                        inspect_elf(executable)
                    if sink:
                        sink('end', item, b'')
                seen.add(name)
            padding = (-length) % 512
            if padding:
                require(read(padding) == bytes(padding), 'nonzero member padding')
            index += 1
        require(manifest is not None and seen == set(expected), 'missing payload members')
        result_hash = package_hash.hexdigest()
        if expected_sha256 is not None:
            require(type(expected_sha256) is str and HEX.fullmatch(expected_sha256), 'invalid expected package hash')
            require(result_hash == expected_sha256, 'package SHA-256 mismatch')
        require(stream.tell() == identity[0], 'archive length changed')
    return {'manifest': manifest, 'sha256': result_hash, 'payload_files': len(seen), 'status': 'verified_integrity_only'}


def pack_package(root, manifest, output):
    validate_manifest(manifest)
    root, output = Path(root), Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive output: partial artifact is removed; existing packages are never clobbered.
    created = False
    try:
        with output.open('xb') as raw:
            created = True
            with tarfile.open(fileobj=raw, mode='w', format=tarfile.USTAR_FORMAT) as archive:
                def add(name, data, length):
                    info = tarfile.TarInfo(name); info.size = length; info.mode = 0o644
                    info.uid = info.gid = info.mtime = 0
                    archive.addfile(info, data)
                data = canonical(manifest)
                require(len(data) <= MAX_MANIFEST, 'manifest exceeds budget')
                add('manifest.json', io.BytesIO(data), len(data))
                for item in sorted(manifest['files'], key=lambda x: x['path']):
                    source = confined(root, item['path'])
                    require(source.stat().st_size == item['size'] and sha_file(source) == item['sha256'], 'staged file changed: ' + item['path'])
                    with source.open('rb') as data:
                        add('payload/' + item['path'], data, item['size'])
        return verify_package(output)
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
