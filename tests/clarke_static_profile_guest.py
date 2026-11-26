#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify installed xsh and dash bindings through a network service restart."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
import tempfile
import threading

from clarke_https_guest import (
    EXECUTABLE, Guest, command, context, create_fat32, exit_browser, load_json,
    resources, root, send_bytes, serve, serve_dns, sha, start_graphics,
    stop_graphics, transact, verify_inputs, verify_package, wait_for_ppm,
)
from iso_dash_install import iso_files
from net_dns_probe_guest import captured_dns_queries
from task_smoke import pump



def https_page(bodies):
    nonce = secrets.token_hex(16)
    index, css, bmp = (f"/{nonce}/{name}" for name in ("index.html", "theme.css", "proof.bmp"))
    pixels = bytes((118, 53, 183)) * (32 * 32)
    bodies[index] = (f'<html><head><title>Static {nonce}</title>'
                     '<link rel="stylesheet" href="theme.css"></head><body>'
                     f'<h1>Authenticated HTTPS</h1><p>{nonce}</p><img src="proof.bmp"></body></html>').encode()
    bodies[css] = b"body { color: #18324c; background-color: #f4f7fc; } h1 { font-size: 24px; }"
    bodies[bmp] = (struct.pack("<2sIHHI", b"BM", 54 + len(pixels), 0, 0, 54)
                   + struct.pack("<IiiHHIIiiII", 40, 32, 32, 1, 24, 0, len(pixels), 0, 0, 0, 0)
                   + pixels)
    return nonce, (index, css, bmp)


def service_started(guest, offset):
    guest.expect(b"[net] ready native_v2=1", start=offset, timeout=60)
    return int(re.search(rb"\[net-start\] pid=(\d+)", guest.output[offset:])[1])


def stop_network(guest):
    answer = command(guest, "net-stop", b"kind=exited code=0", timeout=60)
    if b"[net] close=0" not in answer:
        raise AssertionError("The trusted network service did not close")


def enter_dash(guest):
    begin = len(guest.output)
    send_bytes(guest, b"dash -i\r")
    guest.expect(b"$ ", start=begin, timeout=30)


def leave_dash(guest, baseline):
    end = len(guest.output)
    send_bytes(guest, b"exit\r")
    guest.expect(b"kind=exited code=0", start=end, timeout=30)
    guest.expect_supervisor(start=end)
    pump(guest, 0.1)
    if resources(guest) != baseline:
        raise AssertionError("Dash and browser resources did not return")


def browser_launch(guest, shell, service, baseline, authority, bodies, output, label, *, stale=False):
    nonce, paths = https_page(bodies)
    url = f"https://{authority}{paths[0]}"
    if shell == "dash":
        enter_dash(guest)
        launch = f"/{EXECUTABLE} --network {url}"
        if stale:
            launch = f"XOS_NET_SERVICE_PID={service} {launch}"
    else:
        selector = f"--network-service-pid {service}" if stale else "--network"
        launch = f"clarke.elf {selector} {url}"
    begin = len(guest.output)
    send_bytes(guest, (launch + "\r").encode())
    ready = f"BROWSER_READY engine=litehtml-0.9 local_only=0 javascript=0 network_service={service}"
    guest.expect(ready.encode(), start=begin, timeout=45)
    if stale:
        guest.expect(b"Page error: HTTPS request failed", start=begin, timeout=15)
        if b"BROWSER_LOADED path=" in guest.output[begin:]:
            raise AssertionError("A stale binding became an accepted HTTPS page")
    else:
        guest.expect(f"BROWSER_LOADED path={url}".encode(), start=begin, timeout=15)
        guest.expect(f"BROWSER_TITLE Static {nonce}".encode(), start=begin, timeout=10)
        for path in paths:
            body = bodies[path]
            marker = f"BROWSER_HTTPS status=200 bytes={len(body)} sha256={sha256(body).hexdigest()}"
            guest.expect(marker.encode(), start=begin, timeout=15)
        wait_for_ppm(guest, output / f"{label}.ppm")
    if shell == "dash":
        offset = len(guest.output)
        for down in (True, False):
            guest.qmp("input-send-event", {"events": [{"type": "key", "data": {
                "down": down, "key": {"type": "qcode", "data": "esc"}}}]})
        guest.expect(b"$ ", start=offset, timeout=30)
        send_bytes(guest, b"echo DASH_CLARKE_EXIT:$?\r")
        guest.expect(b"\nDASH_CLARKE_EXIT:0", start=offset, timeout=15)
        leave_dash(guest, baseline)
    else:
        exit_browser(guest, begin, baseline)
    return {
        "pid": service, "resources": baseline,
        **({"refused": True} if stale else {
            "paths": paths, "scanout_sha256": sha(output / f"{label}.ppm"),
        }),
    }


def ordinary_shells(args, installed, output):
    manifest = load_json(args.ordinary_system / "manifest.json")
    sdk = load_json(args.ordinary_system / "sdk/manifest.json")
    config = sdk["network_service"]
    image = args.ordinary_system / "xos-install.iso"
    if config.get("static_profile") or config.get("dns_probe") or not config.get("enabled"):
        raise ValueError("Expected the ordinary N2 image")
    if sha(image) != manifest["artifacts"][image.name]["sha256"]:
        raise ValueError("Ordinary image differs from its manifest")
    for name, expected in manifest["sources"].items():
        if sha(args.system_source / name) != expected:
            raise ValueError("Ordinary source differs from its manifest: " + name)
    guest = Guest(image, "ordinary", work_disk=installed, log_dir=output)
    try:
        guest.expect(b"xos64> ", timeout=60)
        send_bytes(guest, b"run\r")
        guest.expect_supervisor(trace=True, timeout=60)
        command(guest, "demo quiet", b"demo tasks")
        baseline = resources(guest)
        result = command(guest, "clarke.elf --network", b"kind=exited code=2")
        if b"network binding unavailable in this shell" not in result or b"BROWSER_READY" in result:
            raise AssertionError("Ordinary Xsh launched a browser with an unavailable binding")
        enter_dash(guest)
        offset = len(guest.output)
        send_bytes(guest, b'test -z "${XOS_NET_SERVICE_PID+x}" && echo DASH_NETWORK_ENV_ABSENT\r')
        guest.expect(b"\nDASH_NETWORK_ENV_ABSENT", start=offset, timeout=30)
        guest.expect(b"$ ", start=offset, timeout=30)
        send_bytes(guest, f"/{EXECUTABLE} --network\r".encode())
        guest.expect(b"network binding unavailable in this shell", start=offset, timeout=30)
        send_bytes(guest, b"echo DASH_CLARKE_EXIT:$?\r")
        guest.expect(b"\nDASH_CLARKE_EXIT:2", start=offset, timeout=30)
        leave_dash(guest, baseline)
    finally:
        guest.close()
    return {"build_id": manifest["build_id"], "iso_sha256": sha(image), "environment_absent": ["xsh", "dash"]}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "ordinary-system", "system-source", "install-iso", "install-manifest", "payload",
                 "package", "profile", "certificates", "static-profile", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(root / "build")
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "failed", "boots": []}
    stopped, rejected = threading.Event(), threading.Event()
    listener = dns = None
    workers = []
    try:
        system, browser, receipt = verify_inputs(args, installed_static=True)
        sdk = load_json(args.system / "sdk/manifest.json")
        profile = sdk["network_service"]["static_profile"]
        if sdk["network_service"].get("dns_probe") or profile["source_sha256"] != sha(args.static_profile):
            raise ValueError("Expected the sealed profile input for this installed image")
        if browser["address_source"] != "net2_dns" or profile["resolver"] == browser["ipv4_address"]:
            raise ValueError("Use distinct resolver and HTTPS destinations")
        installer = load_json(args.install_manifest)
        files = iso_files(args.install_iso)
        if (installer["build_id"] != system["build_id"] or
                installer["kernel_sha256"] != system["artifacts"]["kernel.bin"]["sha256"] or
                files["KERNEL.BIN"] != installer["kernel_sha256"] or
                files["DASH.ELF"] != installer["dash_sha256"]):
            raise ValueError("Install medium does not contain the bound system and dash")
        sdk_profile = load_json(args.profile)
        package = verify_package(args.package, sdk_profile)
        members = {item["path"]: item["sha256"] for item in package["manifest"]["files"]}
        if package["manifest"]["id"] != "xos.clarke" or members.get(EXECUTABLE) != sha(args.payload):
            raise ValueError("Install package does not contain the exact ClarkE payload")
        for name, digest in load_json(root / "src/ports/native_tls/source_lock.json")["notices"].items():
            member = f"usr/share/licenses/xos.clarke/native_tls/{name}"
            if member not in package["manifest"]["licenses"] or members.get(member) != digest:
                raise ValueError("ClarkE is missing a locked TLS notice")

        host, port = browser["host"], browser["port"]
        authority = host if port == 443 else f"{host}:{port}"
        trace = dict(requests=[], sni=[], handshake_errors=[], dns=[], connections=0, closed=0)
        result.update(system_build_id=system["build_id"], iso_sha256=sha(args.install_iso),
                      installer_manifest_sha256=sha(args.install_manifest), dash_sha256=installer["dash_sha256"],
                      sdk_profile_sha256=sha(args.profile), sealed_profile=profile, browser_profile=browser,
                      browser_sha256=sha(args.payload), browser_receipt_sha256=sha(receipt),
                      package_sha256=package["sha256"], host=trace)
        bodies = {}
        state = {"certificate": "valid", "dns_address": browser["ipv4_address"]}
        tls = {"valid": context(args.certificates, "valid", host, trace["sni"])}
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(4)
        listener.settimeout(0.25)
        dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dns.bind(("127.0.0.1", 53))
        dns.settimeout(0.25)

        def worker(function, key, *parameters):
            try:
                function(*parameters)
            except Exception as error:
                trace[key] = str(error)

        for function, key, parameters in (
            (serve, "error", (listener, tls, state, authority, bodies, trace, stopped, rejected)),
            (serve_dns, "dns_error", (dns, host, state, trace, stopped)),
        ):
            thread = threading.Thread(target=worker, args=(function, key, *parameters), daemon=True)
            thread.start()
            workers.append(thread)

        with tempfile.TemporaryDirectory(prefix="clarke-static-") as folder:
            source, installed = Path(folder) / "source.img", Path(folder) / "installed.img"
            create_fat32(source, 512)
            result["installation"] = transact(source, installed, sdk_profile, "install", package=args.package)
            result["installation"].pop("output", None)
            for shell in ("xsh", "dash"):
                boot = {"shell": shell}
                result["boots"].append(boot)
                capture = output / f"{shell}.pcap"
                guest = Guest(args.install_iso, shell, work_disk=installed, network=True,
                              network_capture=capture, log_dir=output)
                try:
                    guest.expect(b"xos64> ", timeout=60)
                    offset = len(guest.output)
                    send_bytes(guest, b"run\r")
                    guest.expect_supervisor(trace=True, start=offset, timeout=60)
                    if shell == "xsh" and b"[files] dash installed" not in guest.output[offset:]:
                        raise AssertionError("Trusted install medium did not install dash")
                    old = service_started(guest, offset)
                    command(guest, "net-start 42", b"net: device differs from installed static profile")
                    command(guest, "demo quiet", b"demo tasks")
                    display, compositor = start_graphics(guest)
                    boot["initial"] = browser_launch(guest, shell, old, resources(guest), authority,
                                                     bodies, output, f"{shell}.initial")
                    stop_network(guest)
                    offset = len(guest.output)
                    command(guest, "net-start 41", b"[net-start] pid=", timeout=60)
                    fresh = service_started(guest, offset)
                    if fresh <= old:
                        raise AssertionError("A reused or older PID was issued within the same boot")
                    baseline = resources(guest)
                    before_stale = len(trace["requests"]), len(trace["dns"]), trace["connections"]
                    boot["stale"] = browser_launch(guest, shell, old, baseline, authority,
                                                   bodies, output, f"{shell}.stale", stale=True)
                    if before_stale != (len(trace["requests"]), len(trace["dns"]), trace["connections"]):
                        raise AssertionError("A stale binding reached the private peer")
                    boot["rebound"] = browser_launch(guest, shell, fresh, baseline, authority,
                                                     bodies, output, f"{shell}.rebound")
                    stop_graphics(guest, display, compositor)
                    stop_network(guest)
                    boot["service_closed"] = True
                    result["qemu_version"] = subprocess.check_output([guest.command[0], "--version"], text=True).splitlines()[0]
                finally:
                    guest.close()
                if captured_dns_queries(capture) != 2 or captured_dns_queries(capture, profile["resolver"]) != 2:
                    raise AssertionError("Both legitimate bindings must resolve through the sealed peer")
                boot.update(dns_destination=profile["resolver"], captured_dns_requests=2)
            result["ordinary"] = ordinary_shells(args, installed, output)
        paths = [path for boot in result["boots"] for phase in ("initial", "rebound") for path in boot[phase]["paths"]]
        if (trace.get("error") or trace.get("dns_error") or trace["requests"] != paths or
                trace["connections"] != 12 or trace["closed"] != 12 or trace["handshake_errors"] or
                trace["sni"] != [host] * 12 or trace["dns"] != [{"name": host, "answer": state["dns_address"]}] * 4):
            raise AssertionError(f"Unexpected private DNS or HTTPS exchange: {trace}")
        result["status"] = "passed"
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        stopped.set()
        for sock in (dns, listener):
            if sock:
                sock.close()
        for thread in workers:
            thread.join(timeout=6)
        (output / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS: installed xsh and dash reject stale network bindings and acquire the replacement")


if __name__ == "__main__":
    main()
