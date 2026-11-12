# SPDX-License-Identifier: Apache-2.0
"""Exercise the real ABI probe CLI's immutable input/output boundary."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

repo_root = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, default=repo_root / "scripts/build_cpp_abi_probe.py")
    parser.add_argument("--smoke-script", type=Path, default=repo_root / "tests/cpp_abi_smoke.py")
    args = parser.parse_args()
    for script in (args.script, args.smoke_script):
        check_output_boundary(script)
    check_stale_smoke_report(args.smoke_script)
    print("PASS C++ ABI build/smoke output: SDK/runtime remain immutable after rejected output paths")


def check_output_boundary(script):
    with tempfile.TemporaryDirectory(prefix="xos_cpp_abi_output_") as temporary:
        directory = Path(temporary)
        sdk = directory / "sdk"
        runtime = directory / "runtime"
        sdk.mkdir()
        runtime.mkdir()
        manifest = runtime / "manifest.json"
        manifest.write_text("{}\n")
        (sdk / "sentinel").write_bytes(b"immutable SDK\n")
        command = [sys.executable, str(script.resolve()), "--sdk", str(sdk),
                   "--runtime-prefix", str(runtime), "--runtime-manifest", str(manifest)]
        before = {path.relative_to(directory): path.read_bytes()
                  for path in directory.rglob("*") if path.is_file()}
        for output in (sdk, sdk / "output", runtime, runtime / "output"):
            result = subprocess.run([*command, "--output-root", str(output)],
                                    capture_output=True, text=True, check=False)
            assert result.returncode == 2, result
            assert "output-root must not be inside" in result.stderr, result.stderr
            after = {path.relative_to(directory): path.read_bytes()
                     for path in directory.rglob("*") if path.is_file()}
            assert after == before, f"rejected output-root modified immutable input: {output}"
            assert not (sdk / "output").exists() and not (runtime / "output").exists()
        output = directory / "output"
        result = subprocess.run([*command, "--output-root", str(output)],
                                capture_output=True, text=True, check=False)
        assert result.returncode == 2, result
        report = json.loads((output / "cpp_abi_build_report.json").read_text())
        assert report["status"] == "not_ready", report
        assert "manifest.sdk_manifest" in report["error"], report


def check_stale_smoke_report(script):
    with tempfile.TemporaryDirectory(prefix="xos_cpp_abi_stale_") as temporary:
        directory = Path(temporary)
        sdk = directory / "sdk"
        runtime = directory / "runtime"
        output = directory / "output"
        for path in (sdk, runtime, output):
            path.mkdir()
        manifest = runtime / "manifest.json"
        manifest.write_text("{}\n")
        previous = output / "cpp_abi_build_report.json"
        previous.write_text(json.dumps({"status": "partial_not_ready", "features": {}}))
        os.utime(previous, (1, 1))
        result = subprocess.run([sys.executable, str(script.resolve()), "--sdk", str(sdk),
                                 "--runtime-prefix", str(runtime), "--runtime-manifest", str(manifest),
                                 "--output-root", str(output), "--features", "unknown_feature", "--run-guest"],
                                capture_output=True, text=True, check=False)
        report = json.loads((output / "cpp_abi_smoke_report.json").read_text())
        assert report.get("report_error") == "builder report predates this invocation", report
        assert result.returncode == 1 and report["status"] == "failed", result
        assert report["guest_execution"] == "not_run", report


if __name__ == "__main__":
    main()
