#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Open and close the bound Mobius desktop through a persistent Pumpkin login."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))

import pumpkin_user_login as operator
from boot_smoke import Guest
from pumpkin_generation_authority import generation_authority
from work_disk import transfer


class monitor:
    qmp = Guest.qmp

    def __init__(self, address):
        self.qmp_path = str(address)
        self.qmp_socket = None
        self.qmp_file = None

    def close(self):
        if self.qmp_file is not None:
            self.qmp_file.close()
            self.qmp_file = None
        if self.qmp_socket is not None:
            self.qmp_socket.close()
            self.qmp_socket = None

    def press_ctrl(self, key):
        for down, keys in ((True, ("ctrl", key)), (False, (key, "ctrl"))):
            self.qmp("input-send-event", {"events": [
                {"type": "key", "data": {"down": down, "key": {"type": "qcode", "data": code}}}
                for code in keys
            ]})


def frame(observation, image, future, light, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if future.done():
            raise RuntimeError(f"Desktop stopped before scanout, result {future.result()}")
        try:
            observation.qmp("screendump", {"filename": str(image)})
        finally:
            observation.close()
        kind, geometry, depth, pixels = image.read_bytes().split(b"\n", 3)
        if (kind, geometry, depth) == (b"P6", b"800 600", b"255"):
            bright = sum(min(pixels[i:i+3]) > 170 for i in range(0, len(pixels), 3))
            colors = len({pixels[i:i+3] for i in range(0, len(pixels), 3)})
            if colors > 100 and (bright > 100000) == light:
                return {"sha256": operator.digest(image), "colors": colors, "bright_pixels": bright}
        time.sleep(0.25)
    raise AssertionError("Expected Mobius frame did not reach scanout")


def live_desktop(system, state, wallet, output):
    commands, processes, sent = [], [], []
    command = operator.qemu_command
    start = operator.private_vm
    submit = operator.operator_exchange

    def build_command(*args, **kwargs):
        commands.append(kwargs["qmp"])
        return command(*args, **kwargs)

    def start_guest(args):
        vm = start(args)
        processes.append(vm.process)
        return vm

    def track_submission(vm, operation, private_frame, destination, stored):
        submit(vm, operation, private_frame, destination, stored)
        sent.append(stored)

    with (patch.object(operator, "qemu_command", build_command),
          patch.object(operator, "private_vm", start_guest),
          patch.object(operator, "operator_exchange", track_submission)):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(operator.operate, system, state, "desktop", wallet)
            try:
                end = time.monotonic() + 15
                while not future.done() and (not commands or not commands[0].exists()) and time.monotonic() < end:
                    time.sleep(0.1)
                assert commands and commands[0].exists(), "Private desktop QMP did not start"
                screen = monitor(commands[0])
                try:
                    first = frame(screen, output / "midnight.ppm", future, light=False, timeout=140)
                    assert len(sent) == 1 and not any(sent[0]), "The operator retained the submitted wallet"
                    # Let the session span multiple identity polls before using it again.
                    time.sleep(3.1)
                    screen.press_ctrl("d")
                    second = frame(screen, output / "daybreak.ppm", future, light=True, timeout=16)
                    assert first["sha256"] != second["sha256"]
                    screen.press_ctrl("q")
                finally:
                    screen.close()
                assert future.result(timeout=16) == 1
                return {"before": first, "after": second}
            finally:
                if not future.done() and processes and processes[0].poll() is None:
                    processes[0].terminate()


def retire_desktop(system, state, wallet, output):
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="pkadm_") as folder:
        private = Path(folder)
        command = [sys.executable, "-B", str(operator.__file__), "desktop", "--revoke-on-signal",
                   "--system", str(system), "--state", str(state), "--credential-file", str(wallet)]
        with subprocess.Popen(command, env={**os.environ, "TMPDIR": folder}, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) as process:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(process.communicate)
                try:
                    end = time.monotonic() + 15
                    address = None
                    while not future.done() and time.monotonic() < end:
                        address = next(private.glob("pumpkin_user_*/qmp"), None)
                        if address is not None:
                            break
                        time.sleep(0.1)
                    assert address is not None, "Live administration QMP did not start"
                    screen = monitor(address)
                    try:
                        active = frame(screen, output / "active-before-revocation.ppm", future, light=False, timeout=140)
                        time.sleep(2.1)  # The private operator has kept a verified session past its first poll.
                        assert not future.done(), "The desktop closed before the administrator acted"
                        start = time.monotonic()
                        process.send_signal(signal.SIGUSR1)
                        screen.close()
                        stdout, stderr = future.result(timeout=10)
                        elapsed = time.monotonic() - start
                    finally:
                        screen.close()
                    assert process.returncode == 0, stderr
                    assert stdout.splitlines() == [f"Live Pumpkin administration enabled for process {process.pid}",
                                                   "Pumpkin revoked the account and retired the active Mobius session"]
                    return {"active_frame": active, "elapsed_ms": round(elapsed * 1000),
                            "holder_refusal_and_resource_recovery": "confirmed"}
                finally:
                    if not future.done():
                        process.terminate()


def install(state, executable):
    operator.prepare(state)
    disk = state / "work.img"
    transfer(disk, "mkdir", "/usr")
    transfer(disk, "mkdir", "/usr/bin")
    transfer(disk, "import", "/usr/bin/mobius.elf", executable)
    with tempfile.TemporaryDirectory(prefix="pumpkin_mobius_readback_") as folder:
        observed = Path(folder) / "mobius.elf"
        transfer(disk, "export", "/usr/bin/mobius.elf", observed)
        assert operator.digest(executable) == operator.digest(observed)


def run(system, executable, output):
    output.mkdir(parents=True, exist_ok=False)
    binding = operator.bind_system(system)
    manifest = json.loads((system / "manifest.json").read_bytes())
    assert all(operator.digest(root / name) == expected for name, expected in manifest["sources"].items())
    expected = manifest["pumpkin_mobius_executable"]
    assert expected == {"sha256": operator.digest(executable), "bytes": executable.stat().st_size}
    report = {"status": "failed", "build_id": binding[0], "manifest_sha256": binding[1],
              "artifacts": binding[2], "mobius": expected, "runner_sha256": operator.digest(Path(__file__)),
              "operator_sha256": operator.digest(Path(operator.__file__)), "checks": []}
    try:
        command = operator.qemu_command(system / "xos-install.iso", iso=True)
        report["qemu_version"] = subprocess.check_output([command[0], "--version"], text=True).splitlines()[0]
        with tempfile.TemporaryDirectory(prefix="pumpkin_mobius_") as folder:
            private = Path(folder)
            state, wallet = private / "installation", private / "wallet"
            install(state, executable)
            assert operator.operate(system, state, "enroll", wallet) == 1
            authority = generation_authority(state / "authority", operator.realm)
            enrolled = authority.read()
            assert enrolled.revision == 2
            report["scanout"] = live_desktop(system, state, wallet, output)
            assert authority.read() == enrolled
            report["checks"].append("persistent login held through Mobius exit, confirmed logout and resource recovery")
            report["checks"].append("operator wiped its submitted wallet before the first desktop frame")
            assert operator.operate(system, state, "login", wallet) == 1
            report["checks"].append("same credential can authenticate again after logout")
            unaffected = private / "unaffected-wallet"
            assert operator.operate(system, state, "enroll", unaffected, account=b"bob") == 1
            revision = authority.read().revision
            report["live_revocation"] = retire_desktop(system, state, wallet, output)
            assert authority.read().revision == revision + 1
            report["checks"].append("authenticated host administration retired the already-visible desktop and its leases")
            assert operator.operate(system, state, "desktop", wallet) == 2
            assert operator.operate(system, state, "login", unaffected, account=b"bob") == 1
            assert authority.read().revision == revision + 1
            report["checks"].append("durable revocation rejects a later desktop login")
            assert operator.operate(system, state, "revoke", None, account=b"bob") == 1
            assert authority.read().revision == revision + 2
            report["checks"].append("live revocation did not alter the other account or the standalone administrator path")

            modified = private / "different.elf"
            data = executable.read_bytes()
            modified.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
            state, wallet = private / "modified", private / "second-wallet"
            install(state, modified)
            assert operator.operate(system, state, "enroll", wallet) == 1
            try:
                operator.operate(system, state, "desktop", wallet)
            except operator.login_error as error:
                assert str(error) == "Pumpkin desktop could not start or its logout was not confirmed"
            else:
                raise AssertionError("The rebuilt profile accepted different Mobius ELF bytes")
            assert generation_authority(state / "authority", operator.realm).read().revision == 2
            assert operator.operate(system, state, "login", wallet) == 1
            report["checks"].append("same-size changed desktop refused after actual login")
        assert operator.bind_system(system) == binding
        report["status"] = "passed_subset"
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("system", "executable", "output"):
        parser.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    run(args.system.resolve(), args.executable.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
