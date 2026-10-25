# SPDX-License-Identifier: Apache-2.0
import threading
import time


def finish_after_main():
    time.sleep(0.03)
    print("T3_PY_NON_DAEMON_FINISHED")


threading.Thread(target=finish_after_main, name="shutdown-worker").start()
print("T3_PY_MAIN_FINISHED")
