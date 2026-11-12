# SPDX-License-Identifier: Apache-2.0
"""Exercise the real optional newlib builder across interrupted downloads."""
import io
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
newlib_version = "4.6.0.20260123"


class newlib_cache_tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xos_newlib_cache_")
        self.addCleanup(self.temporary.cleanup)
        self.cache = Path(self.temporary.name)
        self.source = self.cache / f"newlib-{newlib_version}"
        binaries = self.cache / "bin"
        binaries.mkdir()
        curl = binaries / "curl"
        curl.write_text('''#!/bin/sh
printf 'download\n' >> "$CACHE/downloads"
if [ -f "$CACHE/network-fail" ]; then
    rm "$CACHE/network-fail"
    exit 28
fi
if [ -f "$CACHE/extract-fail" ]; then
    rm "$CACHE/extract-fail"
    printf 'incomplete archive' > "$CACHE/newlib.tar.gz"
    exit 0
fi
cp "$CACHE/fixture.tar.gz" "$CACHE/newlib.tar.gz"
''')
        curl.chmod(0o755)
        make = binaries / "make"
        make.write_text("#!/bin/sh\nexit 0\n")
        make.chmod(0o755)
        configure = b'#!/bin/sh\n: > "$CACHE/configured"\n'
        with tarfile.open(self.cache / "fixture.tar.gz", "w:gz") as archive:
            info = tarfile.TarInfo(f"newlib-{newlib_version}/configure")
            info.size = len(configure)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(configure))
            for name in ('stdatomic.h', 'tgmath.h'):
                header = repo_root / 'src/third_party/newlib/x86_64-elf/include' / name
                archive.add(header, arcname=f'newlib-{newlib_version}/newlib/libc/include/{name}')
        self.environment = dict(os.environ, CACHE=str(self.cache),
                                PATH=str(binaries) + os.pathsep + os.environ["PATH"])

    def build(self):
        return subprocess.run(["sh", str(repo_root / "scripts/build_newlib.sh")],
                              env=self.environment, capture_output=True, text=True)

    def assert_retry_and_cache(self):
        retried = self.build()
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertTrue((self.cache / "configured").is_file())
        self.assertTrue((self.source / "configure").is_file())
        downloads = (self.cache / "downloads").read_text()
        cached = self.build()
        self.assertEqual(cached.returncode, 0, cached.stderr)
        self.assertEqual((self.cache / "downloads").read_text(), downloads)

    def test_download_failure_can_retry(self):
        (self.cache / "network-fail").touch()
        self.assertEqual(self.build().returncode, 28)
        self.assert_retry_and_cache()

    def test_extract_failure_can_retry(self):
        (self.cache / "extract-fail").touch()
        self.assertNotEqual(self.build().returncode, 0)
        self.assert_retry_and_cache()

    def test_existing_empty_source_can_retry(self):
        self.source.mkdir()
        self.assert_retry_and_cache()


if __name__ == "__main__":
    unittest.main()
