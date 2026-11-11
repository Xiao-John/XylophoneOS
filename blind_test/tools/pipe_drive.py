#!/usr/bin/env python3
"""Run a console program, log output, and forward lines from a FIFO.

Usage: pipe_drive.py --log FILE --fifo FILE -- CMD [ARGS...]
Writes a `.quit` line to stop the child.
"""
import argparse
import datetime as dt
import os
import select
import signal
import subprocess
import sys
import time


def utc():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--fifo", required=True)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        ap.error("missing command")

    try:
        os.unlink(args.fifo)
    except FileNotFoundError:
        pass
    os.mkfifo(args.fifo)

    log = open(args.log, "ab", buffering=0)
    log.write(f"\n===== {utc()} START cmd={cmd!r} =====\n".encode())
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, bufsize=0)
    fifo = os.open(args.fifo, os.O_RDWR | os.O_NONBLOCK)
    os.set_blocking(proc.stdout.fileno(), False)
    started = time.time()
    partial = b""
    last_output = time.time()

    def flush_partial():
        nonlocal partial
        if partial:
            log.write(f"[{utc()}] ".encode() + partial + b"\n")
            partial = b""

    def log_lines(data):
        nonlocal partial, last_output
        last_output = time.time()
        partial += data
        while b"\n" in partial:
            line, partial = partial.split(b"\n", 1)
            log.write(f"[{utc()}] ".encode() + line + b"\n")

    try:
        while True:
            r, _, _ = select.select([proc.stdout.fileno(), fifo], [], [], 0.5)
            if proc.stdout.fileno() in r:
                try:
                    data = os.read(proc.stdout.fileno(), 65536)
                except OSError:
                    data = b""
                if not data:
                    break
                log_lines(data)
            elif partial and time.time() - last_output > 0.25:
                # Prompts such as "xsh> " have no newline.  Flush an idle
                # partial so a completed command is visible before the next
                # input (the old driver waited for the final newline).
                flush_partial()
            if fifo in r:
                try:
                    data = os.read(fifo, 4096)
                except BlockingIOError:
                    data = b""
                if data:
                    log.write(f"[{utc()}] INPUT {data!r}\n".encode())
                    for line in data.splitlines():
                        if line.strip() == b".quit":
                            proc.send_signal(signal.SIGTERM)
                            continue
                        proc.stdin.write(line + b"\r")
                        proc.stdin.flush()
            if proc.poll() is not None:
                # Drain remaining output.
                while True:
                    data = proc.stdout.read(65536)
                    if not data:
                        break
                    log_lines(data)
                break
            if time.time() - started > 7200:
                log.write(f"\n===== {utc()} TIMEOUT 7200s =====\n".encode())
                break
    finally:
        flush_partial()
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.write(f"\n===== {utc()} EXIT returncode={proc.returncode} =====\n".encode())
        os.close(fifo)
        try:
            os.unlink(args.fifo)
        except OSError:
            pass
        log.close()


if __name__ == "__main__":
    main()
