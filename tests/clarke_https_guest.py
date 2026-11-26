#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify authenticated HTTPS navigation in the actual Qt ClarkE guest."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import secrets
import socket
import ssl
import struct
import tempfile
import threading

from aurora_browser_http_guest import (
    Guest, command, create_fat32, exit_browser, resources, root, send_bytes,
    sha, start_graphics, stop_graphics, wait_for_scanout,
)
from xypm_format import load_json, verify_package
from xypm_image import transact


EXECUTABLE = "usr/bin/clarke.elf"


def verify_inputs(args):
    manifest = json.loads((args.system / "manifest.json").read_text())
    for path, digest in manifest["sources"].items():
        if sha(args.system_source / path) != digest:
            raise ValueError("System source mismatch: " + path)
    for path, artifact in manifest["artifacts"].items():
        if sha(args.system / path) != artifact["sha256"]:
            raise ValueError("System artifact mismatch: " + path)
    sdk = json.loads((args.system / "sdk/manifest.json").read_text())
    if not sdk.get("network_service", {}).get("enabled"):
        raise ValueError("The system must include the locked N2 service")
    receipt = args.payload.with_suffix(".receipt.json")
    build = json.loads(receipt.read_text())
    profile = build["network_profile"]["controlled_tls"]
    anchor = ssl.PEM_cert_to_DER_cert((args.certificates / "root.pem").read_text())
    if build["elf_sha256"] != sha(args.payload) or sha256(anchor).hexdigest() != profile["root_der_sha256"]:
        raise ValueError("ClarkE ELF or compiled trust anchor differs")
    if build["network_profile"]["service_wire_version"] != 2 or profile["ipv4_address"] != "10.0.2.2":
        raise ValueError("Expected N2 and the QEMU loopback gateway")
    builder = "/src/ports/aurora_browser/glibc/build.py"
    recorded = next(Path(path).parents[4] for path in build["inputs"] if path.endswith(builder))
    for path, digest in build["inputs"].items():
        path = Path(path)
        if path.is_relative_to(recorded) and sha(root / path.relative_to(recorded)) != digest:
            raise ValueError("Browser source mismatch: " + str(path.relative_to(recorded)))
    for path in ("src/shared/include/xos/net_service_abi.hpp",
                 "src/user/include/xos/net_service_client.hpp", "src/user/include/xos/net_transport.hpp"):
        if build["inputs"][str(recorded / path)] != manifest["sources"][path]:
            raise ValueError("Browser and system disagree on " + path)
    return manifest, profile, receipt


def context(certs, name, host, sni_names):
    result = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    result.minimum_version = ssl.TLSVersion.TLSv1_3
    result.maximum_version = ssl.TLSVersion.TLSv1_3
    result.load_cert_chain(certs / f"{name}-chain.pem", certs / f"{name}.key")

    def sni(_peer, actual, _context):
        sni_names.append(actual)
        return None if actual == host else ssl.ALERT_DESCRIPTION_UNRECOGNIZED_NAME

    result.set_servername_callback(sni)
    return result


def serve(listener, contexts, state, authority, bodies, trace, stopped, untrusted_complete):
    while not stopped.is_set():
        try:
            raw, _ = listener.accept()
        except TimeoutError:
            continue
        except OSError:
            if stopped.is_set():
                return
            raise
        with raw:
            raw.settimeout(6)
            trace["connections"] += 1
            certificate = state["certificate"]
            try:
                peer = contexts[certificate].wrap_socket(raw, server_side=True)
            except ssl.SSLError as error:
                trace["handshake_errors"].append(error.reason)
                if certificate == "unknown-ca":
                    untrusted_complete.set()
                continue
            with peer:
                packet = bytearray()
                while b"\r\n\r\n" not in packet:
                    chunk = peer.recv(512)
                    if not chunk or len(packet) + len(chunk) > 4096:
                        raise ValueError("Incomplete or over-budget HTTP request")
                    packet.extend(chunk)
                headers = bytes(packet).split(b"\r\n")
                method, target, version = headers[0].decode("ascii").split(" ")
                if method != "GET" or version != "HTTP/1.1" or (
                    b"Host: " + authority.encode() not in headers or b"Connection: close" not in headers
                ):
                    raise ValueError("Unexpected HTTP request")
                body = bodies[target]
                trace["requests"].append(target)
                peer.sendall((b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n"
                              b"Connection: close\r\n\r\n") % len(body) + body)
                peer.unwrap().close()
                trace["closed"] += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "system-source", "payload", "package", "profile", "certificates", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to(root / "build")
    out.mkdir(parents=True, exist_ok=False)
    report = {"status": "failed", "checks": []}
    trace = {"requests": [], "sni": [], "handshake_errors": [], "connections": 0, "closed": 0}
    stopped = threading.Event()
    untrusted_complete = threading.Event()
    guest = listener = worker = None
    try:
        manifest, profile, receipt = verify_inputs(args)
        sdk_profile = load_json(args.profile)
        package = verify_package(args.package, sdk_profile)
        files = {item["path"]: item["sha256"] for item in package["manifest"]["files"]}
        tls_lock = load_json(root / "src/ports/native_tls/source_lock.json")
        if package["manifest"]["id"] != "xos.clarke" or files.get(EXECUTABLE) != sha(args.payload):
            raise ValueError("XPK does not contain the verified ClarkE payload")
        for name, digest in tls_lock["notices"].items():
            path = f"usr/share/licenses/xos.clarke/native_tls/{name}"
            if path not in package["manifest"]["licenses"] or files.get(path) != digest:
                raise ValueError("XPK is missing a locked TLS notice")
        host, port = profile["host"], profile["port"]
        authority = host if port == 443 else f"{host}:{port}"
        contexts = {name: context(args.certificates, name, host, trace["sni"])
                    for name in ("valid", "unknown-ca")}
        state = {"certificate": "valid"}
        prefix = "/" + secrets.token_hex(16)
        page, css, bmp, mixed = (prefix + name for name in ("/index.html", "/theme.css", "/proof.bmp", "/mixed.html"))
        pixels = bytes((118, 53, 183)) * (32 * 32)
        stamp = (struct.pack("<2sIHHI", b"BM", 54 + len(pixels), 0, 0, 54)
                 + struct.pack("<IiiHHIIiiII", 40, 32, 32, 1, 24, 0, len(pixels), 0, 0, 0, 0)
                 + pixels)
        bodies = {
            page: (f"<html><head><title>HTTPS {prefix}</title>"
                   '<link rel="stylesheet" href="theme.css"></head><body>'
                   f'<h1>Authenticated HTTPS</h1><p>{prefix}</p><img src="proof.bmp"></body></html>').encode(),
            css: b"body { color: #18324c; background-color: #f4f7fc; } h1 { font-size: 24px; }",
            bmp: stamp,
            mixed: (f'<link rel="stylesheet" href="http://10.0.2.2:{port}{css}">'
                    "<h1>Mixed transport</h1>").encode(),
        }
        report.update(build_id=manifest["build_id"], image_sha256=sha(args.system / "xos-install.iso"),
                      browser_sha256=sha(args.payload), receipt_sha256=sha(receipt), profile=profile,
                      package_sha256=package["sha256"], sdk_profile_sha256=sha(args.profile))
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(4)
        listener.settimeout(0.25)

        def worker_main():
            try:
                serve(listener, contexts, state, authority, bodies, trace, stopped, untrusted_complete)
            except Exception as error:
                trace["error"] = str(error)

        worker = threading.Thread(target=worker_main, daemon=True)
        worker.start()
        with tempfile.TemporaryDirectory(prefix="clarke-https-") as folder:
            source, disk = Path(folder) / "source.img", Path(folder) / "guest.img"
            create_fat32(source, 512)
            report["installation"] = transact(source, disk, sdk_profile, "install", package=args.package)
            guest = Guest(args.system / "xos-install.iso", str(out.relative_to(root / "build")) + "/guest",
                          iso=True, network=True, work_disk=disk)
            guest.expect(b"xos64> ", timeout=60)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, "demo quiet", b"demo tasks")
            begin = len(guest.output)
            net = command(guest, "net-start 41", b"[net-start] pid=", timeout=60)
            service = int(re.search(rb"\[net-start\] pid=(\d+)", net)[1])
            guest.expect(b"[net] ready native_v2=1", start=begin, timeout=60)
            display, compositor = start_graphics(guest)
            baseline = resources(guest)

            def launch(route):
                offset = len(guest.output)
                send_bytes(guest, f"exec-file /{EXECUTABLE} --network-service-pid {service} https://{authority}{route}\r".encode())
                guest.expect(b"BROWSER_READY engine=litehtml-0.9 local_only=0", start=offset, timeout=90)
                return offset

            begin = launch(page)
            guest.expect(f"BROWSER_LOADED path=https://{authority}{page}".encode(), start=begin, timeout=15)
            guest.expect(b"BROWSER_STATUS HTTPS page", start=begin, timeout=15)
            for route in (page, css, bmp):
                body = bodies[route]
                marker = f"BROWSER_HTTPS status=200 bytes={len(body)} sha256={sha256(body).hexdigest()}"
                guest.expect(marker.encode(), start=begin, timeout=15)

            def painted(picture):
                colors = {rgb: count for count, rgb in picture.crop((32, 222, 768, 550)).getcolors(800 * 600)}
                return (colors.get((244, 247, 252), 0) > 5000 and colors.get((24, 50, 76), 0) > 30
                        and colors.get((183, 53, 118), 0) >= 32 * 32)

            picture = wait_for_scanout(guest, out / "https.ppm", painted)
            picture.save(out / "https.png")
            report["screenshot_sha256"] = sha(out / "https.png")
            exit_browser(guest, begin, baseline)
            report["checks"].append("authenticated_https_html_css_bmp_and_pixels")

            begin = launch(mixed)
            guest.expect(b"BROWSER_RESOURCE_REJECT css", start=begin, timeout=15)
            exit_browser(guest, begin, baseline)
            report["checks"].append("mixed_transport_stylesheet_denied")

            state["certificate"] = "unknown-ca"
            begin = launch(page)
            guest.expect(b"Page error: HTTPS request failed", start=begin, timeout=15)
            if b"BROWSER_LOADED path=" in guest.output[begin:]:
                raise AssertionError("Untrusted TLS response became a page")
            exit_browser(guest, begin, baseline)
            if not untrusted_complete.wait(timeout=6):
                raise AssertionError(f"Host did not record the certificate rejection: {trace}")
            if (trace.get("error") or trace["requests"] != [page, css, bmp, mixed] or
                    trace["closed"] != 4 or trace["connections"] != 5 or trace["sni"] != [host] * 5 or
                    trace["handshake_errors"] != ["TLSV1_ALERT_UNKNOWN_CA"]):
                raise AssertionError(f"Unexpected HTTPS traffic: {trace}")
            report["checks"].append("untrusted_certificate_denied_before_http")
            stop_graphics(guest, display, compositor)
            stopped_output = command(guest, "net-stop", b"kind=exited code=0", timeout=60)
            if b"[net] close=0" not in stopped_output:
                raise AssertionError("Native network service did not close")
            report["checks"].append("bilateral_tls_close_and_native_resource_recovery")
            report["status"] = "passed"
    except (Exception, SystemExit) as error:
        report["error"] = str(error)
        raise
    finally:
        stopped.set()
        if listener:
            listener.close()
        if worker:
            worker.join(timeout=6)
        if guest:
            (out / "serial.log").write_bytes(guest.output)
            guest.close()
        report["host"] = trace
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: authenticated HTTPS document and subresources in ClarkE")


if __name__ == "__main__":
    main()
