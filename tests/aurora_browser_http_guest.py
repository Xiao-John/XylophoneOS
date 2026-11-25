#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fresh HTTP bytes through N2, native transport and the actual Qt/liteHTML browser.

Requires a matching system built with XOS_LWIP_SOURCE_ARCHIVE and a rebuilt Qt
browser. Records NOT_RUN when preflight or guest startup is unavailable.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import socket
import sys
import tempfile
import threading

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "tests"), str(root / "scripts")]
from boot_smoke import Guest
from graphics_guest import start_graphics, stop_graphics, wait_for_scanout
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system", "payload", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    system, payload, out = (getattr(args, name).resolve() for name in ("system", "payload", "output"))
    out.relative_to(root / "build")
    out.mkdir(parents=True, exist_ok=False)
    report = {"status": "not_run", "runner_sha256": sha(__file__), "checks": [],
              "not_run": ["DNS", "TLS", "redirect_navigation", "remote_keyboard_navigation",
                          "cross_origin_guest_negative", "forced_service_death", "hardware_network",
                          "remote_BMP", "remote_reload_history_tabs", "in_process_budget_reset",
                          "GUI_responsiveness_during_synchronous_fetch"]}
    guest = server = worker = None
    host = {"requests": []}
    stopped = threading.Event()
    try:
        manifest = json.loads((system / "manifest.json").read_text())
        for name, digest in manifest["sources"].items():
            if sha(root / name) != digest:
                raise ValueError("System source mismatch: " + name)
        for name, entry in manifest["artifacts"].items():
            if sha(system / name) != entry["sha256"]:
                raise ValueError("System artifact mismatch: " + name)
        sdk_manifest = json.loads((system / "sdk/manifest.json").read_text())
        if not sdk_manifest.get("network_service", {}).get("enabled"):
            raise ValueError("Build the system with the pinned XOS_LWIP_SOURCE_ARCHIVE")
        receipt_path = payload.with_suffix(".receipt.json")
        receipt = json.loads(receipt_path.read_text())
        if sha(payload) != receipt["elf_sha256"] or receipt.get("network_profile", {}).get("service_wire_version") != 2:
            raise ValueError("Browser ELF or native network build receipt mismatch")
        inputs = receipt["inputs"]
        browser = root / "src/ports/aurora_browser"
        expected_sources = [
            browser / "build.py", browser / "main.cpp", *browser.glob("*.hpp"),
            *sorted((root / "src/ports/browser_http").glob("*.hpp")),
            root / "src/ports/browser_http/http.cpp",
            root / "src/ports/browser_http/transport.cpp",
        ]
        missing = [path.relative_to(root).as_posix() for path in expected_sources
                   if inputs.get(str(path)) != sha(path)]
        if missing:
            raise ValueError("Browser receipt missing current inputs: " + ", ".join(missing))
        for name, digest in inputs.items():
            if sha(name) != digest:
                raise ValueError("Browser input mismatch: " + name)
        nonce = secrets.token_hex(16)
        page_path, css_path = f"/{nonce}/index.html", f"/{nonce}/theme.css"
        css = b"body { color: #18324c; background-color: #f4f7fc; } h1 { font-size: 24px; }"
        page = ("<html><head><title>HTTP " + nonce + "</title>"
                '<link rel="stylesheet" href="theme.css"></head><body>'
                "<h1>Native HTTP</h1><p>" + nonce + "</p></body></html>").encode()
        bodies = {page_path: page, css_path: css}
        report.update(build_id=manifest["build_id"], image_sha256=sha(system / "xos-install.iso"),
                      browser_sha256=sha(payload), receipt_sha256=sha(receipt_path),
                      challenge_sha256={name: hashlib.sha256(body).hexdigest() for name, body in bodies.items()})
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(4)
        server.settimeout(0.25)
        port = server.getsockname()[1]
        authority = f"10.0.2.2:{port}"

        def serve():
            try:
                while not stopped.is_set():
                    try:
                        connection, _ = server.accept()
                    except socket.timeout:
                        continue
                    with connection:
                        connection.settimeout(5)
                        request = b""
                        while b"\r\n\r\n" not in request and len(request) <= 4096:
                            part = connection.recv(1024)
                            if not part:
                                raise ValueError("Guest closed before HTTP request headers")
                            request += part
                        lines = request.decode("ascii").split("\r\n")
                        method, target, protocol = lines[0].split(" ")
                        if method != "GET" or protocol != "HTTP/1.1" or target not in bodies:
                            raise ValueError("Unexpected guest request: " + lines[0])
                        headers = {}
                        for line in lines[1:]:
                            if not line:
                                break
                            name, value = line.split(":", 1)
                            if name.lower() in headers:
                                raise ValueError("Duplicate request header")
                            headers[name.lower()] = value.strip()
                        if headers.get("host") != authority or headers.get("connection", "").lower() != "close":
                            raise ValueError("HTTP authority/close contract mismatch")
                        body = bodies[target]
                        head = (f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n"
                                "Connection: close\r\n\r\n").encode()
                        # Split actual network writes across framing and body boundaries.
                        connection.sendall(head[:11])
                        connection.sendall(head[11:] + body[:7])
                        connection.sendall(body[7:])
                        connection.shutdown(socket.SHUT_WR)
                        if connection.recv(1) != b"":
                            raise ValueError("Unexpected bytes after the GET")
                        host["requests"].append(target)
            except Exception as error:
                if not stopped.is_set():
                    host["error"] = str(error)

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        with tempfile.TemporaryDirectory(prefix="xos_browser_http_") as temporary:
            disk = Path(temporary) / "work.img"
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "mkdir", "/web")
            transfer(disk, "import", "/bin/aurora.elf", payload)
            for path in (root / "src/ports/aurora_browser/pages").iterdir():
                transfer(disk, "import", "/web/" + path.name, path)
            guest = Guest(system / "xos-install.iso", str(out.relative_to(root / "build")) + "/guest",
                          iso=True, network=True, work_disk=disk)
            report["status"] = "failed"
            report["qemu_command"] = guest.command
            guest.expect(b"xos64> ", timeout=60)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, "demo quiet", b"demo tasks")
            begin = len(guest.output)
            output = command(guest, "net-start 41", b"[net-start] pid=", timeout=60)
            service_pid = int(re.search(rb"\[net-start\] pid=(\d+)", output)[1])
            guest.expect(b"[net] ready native_v2=1", start=begin, timeout=60)
            display, compositor = start_graphics(guest)
            baseline = resources(guest)
            url = "http://" + authority + page_path
            for cycle in range(3):
                begin = len(guest.output)
                send_bytes(guest, f"exec-file /bin/aurora.elf --network-service-pid {service_pid} {url}\r".encode())
                guest.expect(b"BROWSER_LOADED path=" + url.encode(), start=begin, timeout=90)
                guest.expect(b"BROWSER_READY engine=litehtml-0.9 local_only=0", start=begin, timeout=90)
                for name, digest in report["challenge_sha256"].items():
                    guest.expect(f"BROWSER_HTTP status=200 bytes={len(bodies[name])} sha256={digest}".encode(), start=begin)
                guest.expect(("BROWSER_CSS_LOADED path=http://" + authority + css_path).encode(), start=begin)
                pump(guest, 0.3)
                if cycle == 0:
                    screenshot = out / "http-browser.ppm"
                    # The DOM can be ready while the backing-store frame is still in flight.
                    def painted(picture):
                        if picture.size != (800, 600):
                            return False
                        colors = {rgb: count for count, rgb in picture.crop((32, 222, 768, 550)).getcolors(800 * 600)}
                        return colors.get((244, 247, 252), 0) > 5000 and colors.get((24, 50, 76), 0) > 30

                    picture = wait_for_scanout(guest, screenshot, painted)
                    picture.save(out / "http-browser.png")
                    report["screenshot_sha256"] = sha(out / "http-browser.png")
                    report["checks"].append("remote_stylesheet_background_and_text_pixels")
                for down in (True, False):
                    guest.qmp("input-send-event", {"events": [{"type": "key", "data": {
                        "down": down, "key": {"type": "qcode", "data": "esc"}}}]})
                guest.expect(b"kind=exited code=0", start=begin, timeout=30)
                guest.expect_supervisor(start=begin)
                pump(guest, 0.1)
                if resources(guest) != baseline:
                    raise AssertionError("Browser/IPC resources did not return after exit")
                report["checks"].append(f"fresh_http_css_render_close_resources_cycle_{cycle}")
            if host.get("error") or sorted(host["requests"]) != sorted([page_path, css_path] * 3):
                raise AssertionError(str(host))
            stop_graphics(guest, display, compositor)
            stopped_output = command(guest, "net-stop", b"kind=exited code=0", timeout=60)
            if b"[net] close=0" not in stopped_output:
                raise AssertionError(stopped_output[-2000:])
            report["checks"].append("service_reset_close")
            report["status"] = "passed"
    except (Exception, SystemExit) as error:
        report["error"] = str(error)
        raise
    finally:
        stopped.set()
        if server:
            server.close()
        if worker:
            worker.join(timeout=6)
            if worker.is_alive() and report["status"] == "passed":
                report["status"] = "failed"
                report["error"] = "Host HTTP worker did not terminate"
        report["host"] = host
        if guest:
            (out / "serial.log").write_bytes(guest.output)
            guest.close()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "passed":
        raise SystemExit("Guest qualification did not pass")
    print("PASS: fresh native HTTP/CSS in the real browser, three exits and exact resources")


if __name__ == "__main__":
    main()
