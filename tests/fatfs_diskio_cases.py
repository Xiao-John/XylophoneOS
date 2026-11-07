# SPDX-License-Identifier: Apache-2.0
"""Host regression for FatFs diskio sector-boundary arithmetic."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "build/fatfs_diskio"
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / "tests/fixtures/fatfs_diskio/diskio_cases.cpp"
    diskio = ROOT / "src/user/services/fatfs_diskio.cpp"
    command = [shutil.which("clang++") or "c++", "-std=c++17", "-O1", "-w",
               "-I" + str(ROOT / "src/third_party/fatfs"),
               "-I" + str(ROOT / "src/user/include"),
               "-I" + str(ROOT / "src/shared/include"),
               str(source), str(diskio), "-o", str(out / "diskio_cases")]
    subprocess.run(command, check=True)
    run = subprocess.run([str(out / "diskio_cases")], check=True, capture_output=True, text=True)
    report = {
        "status": "passed",
        "scope": "FatFs diskio guard arithmetic with stubbed block calls",
        "guest": "not_run_by_this_runner",
        "output": run.stdout,
        "command": command,
        "sources": {
            "src/user/services/fatfs_diskio.cpp": hashlib.sha256(diskio.read_bytes()).hexdigest(),
            "tests/fixtures/fatfs_diskio/diskio_cases.cpp": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(run.stdout, end="")


if __name__ == "__main__":
    main()
