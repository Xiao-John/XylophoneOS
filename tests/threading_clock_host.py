# SPDX-License-Identifier: Apache-2.0
"""Test threaded clock wrappers with a deterministic nanosleep stub.

Compile the wrapper definitions verbatim; this does not test guest scheduling.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    implementation = (ROOT / 'src/user/threading/pthread.cpp').read_text()
    start = implementation.index('extern "C" int clock_settime(')
    end = implementation.index('extern "C" int clock_gettime(', start)
    with tempfile.TemporaryDirectory(prefix='xos_threading_clock_') as folder:
        folder = Path(folder)
        source = folder / 'probe.cpp'
        source.write_text('''#include <cassert>
#include <cerrno>
#include <initializer_list>
using clockid_t = int;
struct timespec { long tv_sec; long tv_nsec; };
constexpr int CLOCK_REALTIME = 1, CLOCK_MONOTONIC = 4;
static int calls, result, failure;
static const timespec* seen_req;
static timespec* seen_rem;
static int nanosleep(const timespec* req, timespec* rem) {
    ++calls;
    seen_req = req;
    seen_rem = rem;
    if (rem) { *rem = {2, 3}; }
    if (result) { errno = failure; }
    return result;
}
''' + implementation[start:end] + '''
int main() {
    timespec req{0, 123}, rem{7, 8};
    errno = 0;
    assert(clock_settime(CLOCK_REALTIME, &req) == -1 && errno == EPERM);
    errno = 0;
    assert(clock_settime(999, nullptr) == -1 && errno == EPERM);
    for (int flags : {0, 4}) {
        calls = 0;
        errno = 123;
        assert(clock_nanosleep(999, flags, &req, &rem) == EINVAL);
        assert(calls == 0 && errno == 123 && rem.tv_sec == 7 && rem.tv_nsec == 8);
    }
    for (int clock : {CLOCK_REALTIME, CLOCK_MONOTONIC}) {
        calls = 0;
        assert(clock_nanosleep(clock, 4, &req, &rem) == ENOTSUP && calls == 0);
        assert(clock_nanosleep(clock, 8, &req, &rem) == EINVAL && calls == 0);
        assert(clock_nanosleep(clock, 0, nullptr, &rem) == EFAULT && calls == 0);
        for (timespec invalid : {timespec{-1, 0}, {0, -1}, {0, 1000000000}}) {
            assert(clock_nanosleep(clock, 0, &invalid, &rem) == EINVAL && calls == 0);
        }
        result = 0;
        errno = 123;
        assert(clock_nanosleep(clock, 0, &req, &rem) == 0);
        assert(calls == 1 && seen_req == &req && seen_rem == &rem && errno == 123);
        assert(rem.tv_sec == 2 && rem.tv_nsec == 3);
        for (int code : {EINTR, EINVAL, EIO}) {
            result = -1;
            failure = code;
            assert(clock_nanosleep(clock, 0, &req, &rem) == code);
            assert(seen_req == &req && seen_rem == &rem);
            assert(rem.tv_sec == 2 && rem.tv_nsec == 3);
            assert(clock_nanosleep(clock, 0, &req, nullptr) == code);
            assert(seen_rem == nullptr);
        }
    }
}
''')
        executable = folder / 'probe'
        subprocess.run([os.environ.get('CXX', 'g++'), '-std=c++20', '-Wall',
                        '-Wextra', '-Werror', '-fsanitize=undefined',
                        '-fno-sanitize-recover=all', str(source), '-o',
                        str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
    print('threading_clock_host: passed')


if __name__ == '__main__':
    main()
