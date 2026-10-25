# SPDX-License-Identifier: Apache-2.0
import threading


seen = []


def hook(args):
    seen.append((args.thread.name, args.exc_type.__name__, str(args.exc_value)))


threading.excepthook = hook


def fail():
    raise RuntimeError("t3 worker marker")


worker = threading.Thread(target=fail, name="expected-worker")
worker.start()
worker.join()
assert seen == [("expected-worker", "RuntimeError", "t3 worker marker")]
print("T3_PY_EXCEPTION_OK")
