# SPDX-License-Identifier: Apache-2.0
"""Host-level POSIX file semantics over the production files.cpp and real FatFs."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_work_disk import make_image


def main():
    out = ROOT / "build/file_semantics"
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / "tests/fixtures/file_semantics/file_semantics.cpp"
    command = [shutil.which("clang++") or "c++", "-std=c++17", "-O1", "-w",
               "-I" + str(ROOT / "src/third_party/fatfs"),
               "-I" + str(ROOT / "src/user/include"),
               "-I" + str(ROOT / "src/shared/include"),
               str(source), str(ROOT / "src/third_party/fatfs/ff.c"),
               str(ROOT / "src/user/services/fatfs_unicode.cpp"),
               "-o", str(out / "file_semantics")]
    subprocess.run(command, check=True)
    with tempfile.TemporaryDirectory(prefix="xos_file_semantics_") as temp:
        image = Path(temp) / "private.img"
        image.write_bytes(make_image())
        run = subprocess.run([str(out / "file_semantics"), str(image)],
                             check=True, capture_output=True, text=True)
    paths = ["src/user/services/files.cpp",
             "tests/fixtures/file_semantics/file_semantics.cpp",
             "src/third_party/fatfs/ff.c"]
    report = {
        "status": "passed",
        "scope": "production file service with real host FatFs over a private memory image",
        "guest": "not_run_by_this_runner",
        "output": run.stdout,
        "command": command,
        "sources": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths},
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(run.stdout, end="")


if __name__ == "__main__":
    main()
