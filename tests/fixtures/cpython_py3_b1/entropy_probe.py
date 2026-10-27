# SPDX-License-Identifier: Apache-2.0
"""Exercise XOS secure entropy through CPython's normal OS interfaces."""

import os
import sys

if len(sys.argv) > 1 and sys.argv[1] == "unsupported":
    try:
        os.urandom(32)
    except NotImplementedError as error:
        assert "urandom" in str(error), error
        print("PY3_B1_UNSUPPORTED_FAILURE_OK")
    else:
        raise AssertionError("os.urandom unexpectedly succeeded without RDRAND")
    raise SystemExit(0)

for count in (0, 1, 7, 8, 31, 32, 255, 256, 512):
    sample = os.urandom(count)
    assert isinstance(sample, bytes) and len(sample) == count

import random
import secrets
import statistics

assert statistics.mean([2, 4, 6]) == 4
assert random.randrange(10) in range(10)
assert 0 <= secrets.randbelow(1000) < 1000
print("PY3_B1_ENTROPY_STATISTICS_RANDOM_SECRETS_OK")
