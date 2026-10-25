# SPDX-License-Identifier: Apache-2.0
import threading
import time


progress = 0
progress_lock = threading.Lock()
ready = threading.Event()
stop = threading.Event()


def background_progress():
    global progress
    ready.set()
    while not stop.is_set():
        with progress_lock:
            progress += 1
        time.sleep(0)


worker = threading.Thread(target=background_progress, name="io-peer")
worker.start()
assert ready.wait(2.0)
with progress_lock:
    before = progress
progress_windows = 0
with open("/work/t3_py/io_payload.bin", "rb", buffering=0) as stream:
    data = bytearray()
    while True:
        block = stream.read(4096)
        if not block:
            break
        with progress_lock:
            if progress > before:
                progress_windows += 1
            before = progress
        data.extend(block)
with progress_lock:
    after = progress
stop.set()
worker.join()
assert len(data) == 256 * 1024
assert data[:4] == b"XOS!" and data[-4:] == b"T3PY"
assert after > before
# The background thread must make progress across multiple file-service RPC
# waits, not merely before the first read or after the last one.
assert progress_windows >= 3
print("T3_PY_BLOCKING_IO_OK")
