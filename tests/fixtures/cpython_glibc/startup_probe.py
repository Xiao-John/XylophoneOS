# SPDX-License-Identifier: Apache-2.0
import _thread
import sys
import time

assert sys.version_info[:3] == (3, 14, 9)
assert sys.platform == "xos"
assert sum(range(7)) == 21
print("CPYTHON_G4_START", sys.version.split()[0], sys.platform, flush=True)

clock = time.CLOCK_PROCESS_CPUTIME_ID
assert time.clock_getres(clock) > 0
before = time.clock_gettime_ns(clock)
result = sum(value * value for value in range(100000))
assert result == 333328333350000
after = time.clock_gettime_ns(clock)
assert after > before and time.process_time_ns() >= after
start = time.monotonic_ns()
time.sleep(0.025)
assert time.monotonic_ns() - start >= 25000000
print("CPYTHON_G4_CLOCK_PASS", flush=True)

done = _thread.allocate_lock()
done.acquire()
values = []
def worker():
    try:
        before = time.thread_time_ns()
        for _ in range(8):
            assert sum(value * value for value in range(100000)) == 333328333350000
            after = time.thread_time_ns()
            if after > before:
                break
        values.append((before, after, _thread.get_ident(), "guest".upper()))
    finally:
        done.release()

ident = _thread.start_new_thread(worker, ())
assert done.acquire(timeout=5)
assert len(values) == 1 and 0 <= values[0][0] < values[0][1] and values[0][2:] == (ident, "GUEST")
done.release()
print("CPYTHON_G4_THREADS_PASS", flush=True)
