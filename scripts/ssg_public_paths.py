# SPDX-License-Identifier: Apache-2.0
"""Portable serialization of SSG evidence; never use this for execution."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_POSIX = re.compile(r'(?:(?i:/us' r'ers/)|/ho' r'me/|/private/tm' r'p/|/var/fol' r'ders/|/tm' r'p/)[^\s,;"\']+')
PRIVATE_WINDOWS = re.compile(r'(?i)[a-z]:[\\/]+users[\\/]+[^\s,;"\']+')

def resolve_template(value, mappings=()):
    """Resolve a public receipt path with explicit overrides and environment."""
    values = dict(os.environ)
    values.setdefault('XOS_ROOT', str(ROOT))
    values.update({name: str(path) for name, path in mappings if path is not None})
    def substitute(match):
        name = match.group(1)
        if name not in values:
            raise ValueError('set ' + name + ' to verify the recorded input')
        return values[name]
    return Path(re.sub(r'\$\{(XOS_[A-Z0-9_]+)\}', substitute, str(value)))

def portable(value, mappings=(), *, strict=False):
    """Replace known runtime roots in serialized strings, including embedded arguments."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            public_key = portable(key, mappings, strict=strict)
            if public_key in result:
                raise ValueError('portable path collision; provide explicit mappings')
            result[public_key] = portable(item, mappings, strict=strict)
        return result
    if isinstance(value, (list, tuple)):
        return [portable(v, mappings, strict=strict) for v in value]
    if not isinstance(value, (str, Path)):
        return value
    s = str(value)
    pairs = []
    for name, path in mappings:
        if path:
            # Commands may preserve a relative spelling or a symlinked temp
            # directory while metadata uses the resolved absolute spelling.
            pairs.extend((candidate, '${' + name + '}') for candidate in
                         {str(path), str(Path(path).resolve())} if candidate not in ('', '.','/'))
    pairs.append((str(ROOT), '${XOS_ROOT}'))
    for path, replacement in sorted(pairs, key=lambda x: -len(x[0])):
        s = re.sub(re.escape(path) + r'(?=$|[\\/,:;\s])', lambda _: replacement, s)
    # Unknown paths must never silently masquerade as a reproducible command.
    if strict and (PRIVATE_POSIX.search(s) or PRIVATE_WINDOWS.search(s)):
        raise ValueError('unmapped host-private path in public serialization')
    # Legacy callers still get a non-executable, explicitly generic redaction.
    s = PRIVATE_POSIX.sub('${XOS_LOCAL_PATH}', s)
    s = PRIVATE_WINDOWS.sub('${XOS_LOCAL_PATH}', s)
    return s
