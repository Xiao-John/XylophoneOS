# SPDX-License-Identifier: Apache-2.0
"""Host-tool cache trusts only a private, owner-controlled directory."""
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import xypm_image as xi  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        xi.tempfile.gettempdir = lambda: str(root)
        planted = root / ('xos_xypm_host_%d' % xi._uid())
        planted.mkdir()
        planted.chmod(0o777)
        used = xi._private_cache_root()
        assert used == planted, 'owned cache root was not tightened'
        mode = stat.S_IMODE(used.stat().st_mode)
        assert used.stat().st_uid == xi._uid() and (mode & 0o077) == 0, oct(mode)
        # A directory owned by somebody else must not be trusted.
        real_uid = xi._uid
        xi._uid = lambda: real_uid() + 1
        fallback = xi._private_cache_root()
        assert fallback != planted, 'accepted a foreign-owned cache root'
        assert (stat.S_IMODE(fallback.stat().st_mode) & 0o077) == 0
        xi._uid = real_uid
        target = root / 'target'
        target.write_bytes(b'keep')
        link = root / 'link'
        link.symlink_to(target)
        xi._write_private(link, b'bad')
        assert target.read_bytes() == b'keep', 'followed a symlink when writing cache'
        assert not link.is_symlink() and link.read_bytes() == b'bad'
        xi._write_private(root / 'plain', b'ok')
        assert (root / 'plain').read_bytes() == b'ok'
    print('XYPm_HOST_CACHE_OK')


if __name__ == '__main__':
    main()
