# SPDX-License-Identifier: Apache-2.0
try:
    import idna
except ModuleNotFoundError:
    print("PY3_A3_ROLLBACK_ABSENT_OK")
else:
    raise AssertionError("xypm remove left idna importable")
