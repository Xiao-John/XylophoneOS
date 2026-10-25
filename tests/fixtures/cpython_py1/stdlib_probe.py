# SPDX-License-Identifier: Apache-2.0
import collections
import functools
import itertools
import json
import math
import re

value = json.loads('{"items": [1, 2, 3], "text": "\\u96ea"}')
assert value["text"] == "雪"
assert re.fullmatch(r"[a-z]+-[0-9]+", "xos-314")
assert collections.Counter("abaca")["a"] == 3
assert list(itertools.accumulate(value["items"])) == [1, 3, 6]
assert functools.reduce(lambda left, right: left * right, value["items"]) == 6
assert math.isclose(math.sqrt(81), 9.0)
print("PY1_STDLIB_OK json re collections itertools functools math 雪")
