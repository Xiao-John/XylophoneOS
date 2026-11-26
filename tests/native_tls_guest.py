#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Controlled native TLS 1.3 and X.509 acceptance in the real XOS guest."""
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src/ports/native_tls")]
from boot_smoke import Guest
from build_probe import NET_HEADERS, sha, verify_hashes
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import pump, send_bytes
from work_disk import transfer

HOSTNAME = "tls.xos.test"
OTHER_NAME = "other.xos.test"
CERT_DENIALS = {"wrong-name", "unknown-ca", "missing-intermediate", "expired"}


def prepare(destination):
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    openssl = shutil.which("openssl")
    if not openssl:
        raise ValueError("OpenSSL with x509 -not_before and -not_after is required")

    def run(*args):
        return subprocess.check_output([openssl, *args], cwd=destination, stderr=subprocess.PIPE)

    for authority in ("root", "other-root"):
        run("req", "-x509", "-newkey", "rsa:2048", "-noenc", "-sha256", "-days", "7",
            "-subj", "/CN=XOS TLS Test " + authority, "-keyout", authority + ".key",
            "-out", authority + ".pem", "-addext", "basicConstraints=critical,CA:TRUE,pathlen:1",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")

    now = datetime.now(timezone.utc)
    for name, issuer, role in (
        ("intermediate", "root", "issuer"),
        ("valid", "intermediate", "leaf"),
        ("expired", "intermediate", "leaf"),
        ("unknown-ca", "other-root", "leaf"),
    ):
        ext = destination / "extensions.cnf"
        ext.write_text(
            "basicConstraints=critical,CA:TRUE,pathlen:0\n"
            "keyUsage=critical,keyCertSign,cRLSign\n"
            "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid\n"
            if role == "issuer" else
            "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n"
            f"extendedKeyUsage=serverAuth\nsubjectAltName=DNS:{HOSTNAME}\n"
        )
        run("req", "-new", "-newkey", "rsa:2048", "-noenc", "-sha256", "-subj",
            "/CN=" + (HOSTNAME if role == "leaf" else "XOS TLS Test Intermediate"),
            "-keyout", name + ".key", "-out", name + ".csr")
        dates = ["-days", "4"]
        if name == "expired":
            fmt = "%Y%m%d%H%M%SZ"
            dates = ["-not_before", (now - timedelta(days=2)).strftime(fmt),
                     "-not_after", (now - timedelta(days=1)).strftime(fmt)]
        run("x509", "-req", "-in", name + ".csr", "-sha256", "-CA", issuer + ".pem",
            "-CAkey", issuer + ".key", "-set_serial", str(secrets.randbits(127) or 1),
            "-out", name + ".pem", "-extfile", ext.name, *dates)

    for name in ("valid", "expired", "unknown-ca"):
        path = destination / (name + ".pem")
        chain = (destination / "intermediate.pem").read_bytes() if name != "unknown-ca" else b""
        (destination / (name + "-chain.pem")).write_bytes(path.read_bytes() + chain)
    run("verify", "-CAfile", "root.pem", "-untrusted", "intermediate.pem",
        "-verify_hostname", HOSTNAME, "valid.pem")
    der = run("x509", "-in", "root.pem", "-outform", "DER")
    header = destination / "tls_test_root.h"
    lines = [", ".join(f"0x{byte:02x}" for byte in der[i:i + 12]) for i in range(0, len(der), 12)]
    header.write_text("static constexpr unsigned char tls_test_root[] = {\n    "
                      + ",\n    ".join(lines) + "\n};\n")
    binding = {"certificate_generator": run("version").decode().strip(),
               "root_der_sha256": sha256(der).hexdigest(),
               "root_header_sha256": sha(header),
               "public_fixtures": {file.name: sha(file) for file in destination.glob("*.pem")}}
    (destination / "certificates.json").write_text(json.dumps(binding, indent=2) + "\n")


def boot(guest):
    guest.expect(b"xos64> ", timeout=60)
    send_bytes(guest, b"run\r")
    guest.expect_supervisor(trace=True, timeout=60)
    command(guest, "demo quiet", b"demo tasks")


def start_network(guest):
    begin = len(guest.output)
    row = command(guest, "net-start 41", b"[net-start] pid=", timeout=60)
    guest.expect(b"[net] ready native_v2=1", start=begin, timeout=60)
    return int(re.search(rb"\[net-start\] pid=(\d+)", row)[1])


def check_resources(guest, baseline):
    for _ in range(12):
        current = resources(guest)
        if current == baseline:
            return
        pump(guest, 0.1)
    raise AssertionError(f"process/IPC counters changed: {current} expected {baseline}")


def exchange(guest, pid, scenario, certificates):
    name = OTHER_NAME if scenario == "wrong-name" else HOSTNAME
    certificate = scenario if scenario in {"expired", "unknown-ca"} else "valid"
    nonce = secrets.token_hex(16)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.num_tickets = 0
    chain_file = "valid.pem" if scenario == "missing-intermediate" else certificate + "-chain.pem"
    context.load_cert_chain(certificates / chain_file,
                            certificates / (certificate + ".key"))
    server = {"application_request": False}

    def sni(_connection, value, _context):
        server["sni"] = value

    context.set_servername_callback(sni)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.listen(1)
        listener.settimeout(35)
        expected = (f"GET /{nonce} HTTP/1.1\r\nHost: {name}:{port}\r\n"
                    "Connection: close\r\n\r\n").encode()

        def serve():
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(25)
                    try:
                        tls = context.wrap_socket(connection, server_side=True)
                    except ssl.SSLError as err:
                        server["handshake_alert"] = err.reason
                        return
                    with tls:
                        server["version"] = tls.version()
                        server["cipher"] = tls.cipher()[0]
                        request = bytearray()
                        while b"\r\n\r\n" not in request and len(request) <= 256:
                            part = tls.recv(256)
                            if not part:
                                break
                            request.extend(part)
                        server["application_request"] = bool(request)
                        if request != expected:
                            raise AssertionError("Unexpected decrypted HTTP request")
                        header = b"HTTP/1.1 200 OK\r\nContent-Length: 32\r\nConnection: close\r\n\r\n"
                        body = nonce.encode()
                        tls.sendall(header[:13])
                        tls.sendall(header[13:] + body[:11])
                        tls.sendall(body[11:])
                        if scenario == "truncated":
                            tls.shutdown(socket.SHUT_WR)
                        else:
                            tls.unwrap().close()
                            server["client_close_notify"] = True
            except Exception as err:
                server["error"] = str(err)

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        before = int(time.time())
        output = command(guest, f"exec-file /bin/tls.elf {pid} {port} {scenario} {nonce}",
                         b"kind=exited code=", timeout=40)
        after = int(time.time())
        worker.join(timeout=5)
        if worker.is_alive():
            raise AssertionError(f"{scenario}: TLS peer did not finish")
    if b"kind=exited code=0" not in output or b"NATIVE_TLS_ERROR" in output or "error" in server:
        raise AssertionError(f"{scenario} failed: {output!r} / {server}")
    guest_wall = int(re.search(rb"NATIVE_TLS_CLOCK realtime=(\d+)", output)[1])
    if not before - 2 <= guest_wall <= after + 2:
        raise AssertionError("Guest clock diverges from the trusted developer host")
    if server.get("sni") != name:
        raise AssertionError(f"{scenario}: TLS SNI mismatch")
    if scenario in CERT_DENIALS:
        required = f"NATIVE_TLS_REJECT scenario={scenario} flags=0x".encode()
        if required not in output or server["application_request"] or "handshake_alert" not in server:
            raise AssertionError(f"{scenario}: missing authenticated certificate refusal")
    else:
        required = (b"NATIVE_TLS_HTTPS status=200 bytes=32 close_notify=verified" if scenario == "valid"
                    else b"NATIVE_TLS_REJECT scenario=truncated")
        if required not in output or server.get("version") != "TLSv1.3" or not server["application_request"]:
            raise AssertionError(f"{scenario}: HTTPS result differs from the TLS peer")
        if scenario == "valid" and not server.get("client_close_notify"):
            raise AssertionError("Peer did not receive the client's TLS close_notify")
    marker = re.search(rb"NATIVE_TLS_(?:HTTPS|REJECT) .*", output)[0].decode().strip()
    return {"scenario": scenario, "guest": marker, "guest_realtime": guest_wall,
            "host_realtime_window": [before, after],
            "peer_certificate_chain_sha256": sha(certificates / chain_file),
            "nonce_sha256": sha256(nonce.encode()).hexdigest(), **server}


def test(system, probe, certificates, output):
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "not_run", "runner_sha256": sha(Path(__file__)),
              "scope": "controlled_ipv4_user_space_tls13", "checks": [],
              "not_run": ["public_CA_store", "production_trusted_time", "hardware_entropy_qualification",
                          "DNS", "NetworkProcess", "concurrent_tls_callers", "HTTP2_HTTP3"]}
    guest = None
    try:
        manifest_path, receipt_path = system / "manifest.json", probe / "receipt.json"
        manifest = json.loads(manifest_path.read_text())
        receipt = json.loads(receipt_path.read_text())
        cert_binding = json.loads((certificates / "certificates.json").read_text())
        verify_hashes(ROOT, manifest["sources"])
        verify_hashes(system, {name: art["sha256"] for name, art in manifest["artifacts"].items()})
        verify_hashes(ROOT, receipt["inputs"])
        verify_hashes(certificates, cert_binding["public_fixtures"])
        elf = probe / "native_tls_probe.elf"
        image = system / "xos-install.iso"
        sdk = json.loads((system / "sdk/manifest.json").read_text())
        if (receipt["status"] != "linked" or receipt["network_wire_version"] != 2 or
            not sdk.get("network_service", {}).get("enabled") or sha(elf) != receipt["elf_sha256"] or
            receipt["test_root_header_sha256"] != cert_binding["root_header_sha256"] or
            sha(certificates / "tls_test_root.h") != cert_binding["root_header_sha256"]):
            raise ValueError("TLS proof, trust anchor, or native network profile is unbound")
        for header in NET_HEADERS:
            if receipt["inputs"][header] != manifest["sources"][header]:
                raise ValueError("TLS/native network input mismatches the system")
        report.update(system_build_id=manifest["build_id"], image_sha256=sha(image),
                      system_manifest_sha256=sha(manifest_path), probe_sha256=sha(elf),
                      probe_receipt_sha256=sha(receipt_path), certificates=cert_binding,
                      sdk_manifest_sha256=receipt["sdk_manifest_sha256"],
                      tls_archive_sha256=receipt["archive_sha256"], peer_tls=ssl.OPENSSL_VERSION)
        with tempfile.TemporaryDirectory(prefix="xos-native-tls-") as tmp:
            disk = Path(tmp) / "work.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", "/bin/tls.elf", elf)
            report["status"] = "failed"
            guest = Guest(image, "guest", iso=True, work_disk=disk, network=True, log_dir=output)
            report["qemu"] = subprocess.check_output([guest.command[0], "--version"], text=True).splitlines()[0]
            report["qemu_command"] = guest.command
            boot(guest)
            pid = start_network(guest)
            baseline = resources(guest)
            for scenario in ("valid", "wrong-name", "unknown-ca", "missing-intermediate",
                             "expired", "truncated", "valid"):
                report["checks"].append(exchange(guest, pid, scenario, certificates))
                check_resources(guest, baseline)
            report["resources_after_every_exchange"] = list(baseline)
            guest.close()
            guest = None

            with socket.socket() as cannot_connect:
                cannot_connect.bind(("127.0.0.1", 0))
                cannot_connect.listen(1)
                cannot_connect.setblocking(False)
                port = cannot_connect.getsockname()[1]
                guest = Guest(image, "no_entropy", cpu="qemu64,-rdrand", iso=True, work_disk=disk,
                              network=True, log_dir=output)
                report["qemu_no_entropy_command"] = guest.command
                boot(guest)
                output_line = command(guest, f"exec-file /bin/tls.elf 1 {port} valid {secrets.token_hex(16)}",
                                      b"XOS glibc: invalid startup or entropy unavailable", timeout=30)
                if b"NATIVE_TLS_CLOCK" in output_line or b"kind=exited code=127" not in output_line:
                    raise AssertionError("No-entropy startup did not fail before main")
                try:
                    rejected, _ = cannot_connect.accept()
                except BlockingIOError:
                    pass
                else:
                    rejected.close()
                    raise AssertionError("Guest connected despite missing CPU entropy")
                report["checks"].append({"scenario": "no_rdrand", "startup": "exited_127_before_network"})
        report["status"] = "passed_subset"
    except Exception as err:
        report["error"] = str(err)
        raise
    finally:
        if guest is not None:
            guest.close()
        logs = {path.name: sha(path) for path in output.glob("*.log")}
        report["logs"] = logs
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("prepare").add_argument("--certificates", type=Path, required=True)
    check = sub.add_parser("test")
    for name in ("system", "probe", "certificates", "output"):
        check.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.certificates.resolve())
    else:
        test(args.system.resolve(), args.probe.resolve(), args.certificates.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
