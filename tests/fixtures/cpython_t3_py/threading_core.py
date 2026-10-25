# SPDX-License-Identifier: Apache-2.0
import queue
import threading


counter = 0
counter_lock = threading.Lock()
idents = set()


def count():
    global counter
    with counter_lock:
        idents.add(threading.get_ident())
    for _ in range(200):
        with counter_lock:
            counter += 1


workers = [threading.Thread(target=count, name=f"counter-{index}") for index in range(2)]
for worker in workers:
    worker.start()
for worker in workers:
    worker.join()
assert counter == 400
assert len(idents) == 2

rlock = threading.RLock()
with rlock:
    with rlock:
        assert rlock._is_owned()

condition = threading.Condition()
condition_ready = threading.Event()
condition_done = []


def condition_worker():
    with condition:
        condition_ready.set()
        assert condition.wait_for(lambda: bool(condition_done), timeout=2.0)


worker = threading.Thread(target=condition_worker, name="condition")
worker.start()
assert condition_ready.wait(2.0)
with condition:
    condition_done.append(True)
    condition.notify()
worker.join()

event = threading.Event()
worker = threading.Thread(target=event.set, name="event")
worker.start()
assert event.wait(2.0)
worker.join()

items = queue.Queue(maxsize=1)
worker = threading.Thread(target=lambda: items.put(("queue", 314)), name="queue")
worker.start()
assert items.get(timeout=2.0) == ("queue", 314)
items.task_done()
worker.join()
items.join()

print("T3_PY_CORE_OK Lock RLock Condition Event Queue")
