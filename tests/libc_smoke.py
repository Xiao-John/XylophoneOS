"""E06: newlib libc printf/malloc/string/exit through the XOS SDK."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from boot_smoke import Guest
from task_smoke import send_bytes, pump


def command(guest, line, expected, timeout=20):
    start = len(guest.output)
    send_bytes(guest, line.encode() + b"\r")
    guest.expect(expected, start=start, timeout=timeout)
    guest.expect(b"sup> ", start=start, timeout=timeout)
    return bytes(guest.output)[start:]


def main():
    build = ROOT / "build"
    manifest = json.loads((build / "manifest.json").read_text())
    checks = []
    report = {"build_id": manifest["build_id"], "checks": checks, "status": "failed"}
    guest = Guest(build / "xos.img", "libc_smoke")
    report["command"] = guest.command
    try:
        guest.expect(b"xos64> ", timeout=20)
        start = len(guest.output)
        send_bytes(guest, b"run\r")
        guest.expect_supervisor(trace=True, start=start, timeout=20)
        guest.expect(b"[sup] demo tasks stopped", timeout=10)
        pump(guest, 0.3)
        images = command(guest, "images", b"image=libc_hello")
        if b"bytes=0" in images:
            raise AssertionError("libc_hello has zero bytes")
        checks.append("libc_program_is_in_image_catalog")

        output = command(guest, "exec libc_hello", b"libc says: malloc+printf 42 beef")
        for marker in (b"second line", b"kind=exited code=7"):
            if marker not in output:
                raise AssertionError(f"libc_hello missing {marker!r}: {output[-600:]!r}")
        checks.append("newlib_printf_malloc_string_and_exit")

        # A second run checks that stdio/heap state was not left corrupted.
        second = command(guest, "exec libc_hello", b"libc says: malloc+printf 42 beef")
        if b"kind=exited code=7" not in second:
            raise AssertionError("second libc run did not exit 7")
        checks.append("libc_heap_and_stdio_are_reusable_across_runs")

        report["status"] = "passed"
        print(f"PASS: {len(checks)} E06 checks | build {manifest['build_id']}")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        guest.close()
        (build / "libc_smoke_report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
