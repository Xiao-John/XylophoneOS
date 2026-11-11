# SPDX-License-Identifier: Apache-2.0
"""Host regression for xypm JSON integer parsing (INT64_MIN/overflow)."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "build/xypm_json"
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / "tests/fixtures/xypm_json/json_cases.cpp"
    command = [shutil.which("clang++") or "c++", "-std=c++17", "-O1", "-w",
               "-I" + str(ROOT / "src/user/include"),
               "-I" + str(ROOT / "src/shared/include"),
               str(source), "-o", str(out / "json_cases")]
    subprocess.run(command, check=True)
    run = subprocess.run([str(out / "json_cases")], check=True, capture_output=True, text=True)
    report = {
        "status": "passed",
        "scope": "xypm JSON integer boundary parsing on the host",
        "guest": "not_run_by_this_runner",
        "output": run.stdout,
        "command": command,
        "sources": {
            "tests/fixtures/xypm_json/json_cases.cpp": hashlib.sha256(source.read_bytes()).hexdigest(),
            "src/user/programs/xypm_native.hpp": hashlib.sha256(
                (ROOT / "src/user/programs/xypm_native.hpp").read_bytes()).hexdigest(),
        },
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(run.stdout, end="")


if __name__ == "__main__":
    main()
