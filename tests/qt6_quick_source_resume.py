#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Kill and resume real Qt source preparation before compiling any Qt code."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/ports/qt6/quick"))
import build_target
from sdk_receipt import sha, tree_receipt


class SourcesReady(Exception):
    pass


def prepare(args):
    run = subprocess.run
    extract = tarfile.TarFile.extract

    def run_or_stop_at_cmake(command, *positional, **kwargs):
        if command[0] == "cmake":
            if command[1] == "-S" and Path(command[2]).parent.name == "qtdeclarative_source":
                raise SourcesReady
            # Only the preparation path is under test. The real QtBase
            # install has a separate build and acceptance receipt.
            if command[1] == "--install":
                libraries = args.output / "target/lib"
                libraries.mkdir(parents=True, exist_ok=True)
                for name in ("Core", "Gui"):
                    (libraries / f"libQt6{name}.a").write_bytes(b"test stand-in")
            return subprocess.CompletedProcess(command, 0)
        result = run(command, *positional, **kwargs)
        if (args.phase == "qtbase" and command[0] == "patch"
                and Path(command[-1]).name == build_target.BASE_PATCHES[0].name):
            print("QtBase first glibc patch applied. Injecting SIGKILL.", flush=True)
            os.kill(os.getpid(), signal.SIGKILL)
        return result

    def extract_or_interrupt(release, member, path, **kwargs):
        result = extract(release, member, path, **kwargs)
        if args.phase == "qtdeclarative" and Path(path).name == "qtdeclarative_source" and member.isfile():
            print("Qt Declarative first file extracted. Injecting SIGKILL.", flush=True)
            os.kill(os.getpid(), signal.SIGKILL)
        return result

    args.resume = args.phase != "qtbase"
    args.jobs = 1
    with (patch.object(subprocess, "run", run_or_stop_at_cmake),
          patch.object(tarfile.TarFile, "extract", extract_or_interrupt)):
        try:
            build_target.rebuild(args)
        except SourcesReady:
            if args.phase == "finish":
                return
            raise
    raise AssertionError("The test must stop before either source tree is compiled")


def verify(args):
    original = json.loads((args.previous_output / "inputs.json").read_text())
    command = [sys.executable, "-B", __file__, *sys.argv[1:], "--phase"]
    base = args.output / "qtbase_source"
    declarative = args.output / "qtdeclarative_source"
    assert not args.output.exists()
    first = subprocess.run([*command, "qtbase"], check=False)
    assert first.returncode == -signal.SIGKILL
    assert not base.exists() and not declarative.exists()
    assert len(list(args.output.glob(".qtbase_source-*"))) == 1
    second = subprocess.run([*command, "qtdeclarative"], check=False)
    assert second.returncode == -signal.SIGKILL
    assert base.is_dir() and not declarative.exists()
    assert len(list(args.output.glob(".qtdeclarative_source-*"))) == 1
    subprocess.run([*command, "finish"], check=True)
    prepared = {}
    for source in (base, declarative):
        expected = tree_receipt(args.previous_output / source.name)
        recovered = tree_receipt(source)
        assert expected == recovered, source.name
        prepared[source.name] = {
            "tree_sha256": recovered["tree_sha256"],
            "files": len(recovered["files"]),
            "directories": len(recovered["directories"]),
        }
    recipe = "src/ports/qt6/quick/build_target.py"
    replay = json.loads((args.output / "inputs.json").read_text())
    original_recipe = original["recipes"].pop(recipe)
    replay_recipe = replay["recipes"].pop(recipe)
    assert original_recipe != replay_recipe == sha(ROOT / recipe)
    assert original == replay
    report = {
        "status": "SOURCE_RESUME_VERIFIED",
        "qtbase_interruption": "SIGKILL after first QtBase glibc patch",
        "qtdeclarative_interruption": "SIGKILL after first real archive file extraction",
        "matches_original_source_trees": prepared,
        "original_builder_sha256": original_recipe,
        "replay_builder_sha256": replay_recipe,
        "scope": "real locked sources and patches through pre-configuration; CMake stubbed",
    }
    (args.output / "source-resume.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("host-kit", "sdk-build", "sdk-profile", "declarative", "previous-output", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--phase", choices=("qtbase", "qtdeclarative", "finish"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.phase:
        prepare(args)
    else:
        verify(args)


if __name__ == "__main__":
    main()
