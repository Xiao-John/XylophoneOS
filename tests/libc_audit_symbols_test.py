# SPDX-License-Identifier: Apache-2.0
"""Check the audit's symbol inventory against a real compiler and archive."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from libc_audit import symbols


@unittest.skipUnless(all(shutil.which(tool) for tool in ("cc", "ar", "nm")),
                     "host cc/ar/nm are required")
class libc_audit_symbol_tests(unittest.TestCase):
    def test_archive_headings_are_not_unresolved_symbols(self):
        with tempfile.TemporaryDirectory(prefix="xos_libc_audit_") as folder:
            root = Path(folder)
            source, obj, archive = (root / name for name in ("probe.c", "probe.o", "libprobe.a"))
            source.write_text("extern int missing(void); int provided(void) { return missing(); }\n")
            subprocess.run(["cc", "-fno-pie", "-c", str(source), "-o", str(obj)], check=True)
            subprocess.run(["ar", "qc", str(archive), str(obj)], check=True)
            self.assertEqual(symbols("-u", str(archive), nm="nm"), ["missing"])
            self.assertEqual(symbols("--defined-only", "-g", str(archive), nm="nm"), ["provided"])


if __name__ == "__main__":
    unittest.main()
