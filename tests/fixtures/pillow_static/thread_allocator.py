# SPDX-License-Identifier: Apache-2.0
"""Isolate baseline CPython/newlib/zlib threading from Pillow."""
import threading
import zlib
errors = []
def worker():
    try:
        for _ in range(80):
            data = bytes(range(256)) * 4
            assert zlib.decompress(zlib.compress(data)) == data
    except BaseException as error:
        errors.append(repr(error))
threads = [threading.Thread(target=worker) for _ in range(2)]
for thread in threads: thread.start()
for thread in threads: thread.join()
assert not errors, errors
print('BASELINE_THREADS_OK', flush=True)
