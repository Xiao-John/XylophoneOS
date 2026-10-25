# SPDX-License-Identifier: Apache-2.0
import threading


started = threading.Event()
stop = threading.Event()


def daemon():
    started.set()
    stop.wait()


worker = threading.Thread(target=daemon, name="daemon", daemon=True)
worker.start()
assert started.wait(2.0)
print("T3_PY_DAEMON_EXIT_OK")
