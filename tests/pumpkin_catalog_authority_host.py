#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the production catalog reader and admission checks with modeled transport."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CASES = ("owner", "native", "wrong_send_peer", "wrong_receive_peer", "wrong_realm",
         "wrong_version", "wrong_sequence", "unavailable", "timeout")


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    paths = [ROOT / "src/user/loader/dynamic/authority.cpp",
             ROOT / "tests/fixtures/pumpkin/catalog_authority_host.cpp"]
    tracked = [*paths, Path(__file__), ROOT / "src/user/loader/dynamic/authority.hpp"]
    tracked += [p for folder in ("src/user/include/xos", "src/shared/include/xos")
                for p in (ROOT / folder).glob("*") if p.suffix in (".hpp", ".h")]
    hashes = lambda: {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    report = {"status": "failed", "scope": "production reader/admission; modeled kernel transport",
              "guest": "not_run", "sources": hashes(), "results": [], "commands": []}
    try:
        for kind in ("ordinary", "sanitized"):
            binary = output / kind
            command = [os.environ.get("CXX", "g++"), "-std=c++20", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                       "-I", str(ROOT / "src/shared/include"), "-I", str(ROOT / "src/user/include"),
                       *map(str, paths), "-o", str(binary)]
            if kind == "sanitized":
                command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
            report["commands"].append(command)
            with (output / (kind + "_compile.log")).open("w") as stream:
                subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
            for case in CASES:
                result = subprocess.run([str(binary), case], capture_output=True, text=True, timeout=20,
                                        env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0:abort_on_error=1",
                                                 UBSAN_OPTIONS="halt_on_error=1"))
                (output / f"{kind}_{case}.log").write_text(result.stdout + result.stderr)
                report["results"].append({"kind": kind, "case": case, "exit": result.returncode})
                assert result.returncode == 0 and f"PASS catalog authority {case}" in result.stdout
                print(result.stdout.strip(), flush=True)
        assert report["sources"] == hashes()
        report["status"] = "passed"
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output.resolve())
