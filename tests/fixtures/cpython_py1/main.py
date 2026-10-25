# SPDX-License-Identifier: Apache-2.0
import os
import sys

import helper

assert sys.argv == ["/work/py1/main.py", "alpha", "beta"]
assert os.getcwd() == "/"
assert os.environ.get("PATH") == "/usr/bin:/bin:/"
assert sys.path[0] == "/work/py1"
assert helper.VALUE == "same-directory"
assert "main.py" in os.listdir("/work/py1")
assert os.stat(__file__).st_size > 0
assert not any("/Users/" in path or ".cache/xos_seed" in path for path in sys.path)
print("PY1_CONTRACT_OK")
print("ARGV=" + repr(sys.argv))
print("CWD=" + os.getcwd())
print("PATH0=" + sys.path[0])
print("ENV_PATH=" + os.environ["PATH"])
