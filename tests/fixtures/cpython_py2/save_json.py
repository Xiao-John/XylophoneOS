# SPDX-License-Identifier: Apache-2.0
import json
import os


path = "/work/py2/save.json"
value = {"version": 2, "player": "雪", "items": ["lamp", "key"], "score": 42}
with open(path, "w", encoding="utf-8") as stream:
    json.dump(value, stream, ensure_ascii=False, sort_keys=True)
with open(path, "r", encoding="utf-8") as stream:
    assert json.load(stream) == value
assert os.stat(path).st_size > 0
print("PY2_SAVE_OK", os.stat(path).st_size)
