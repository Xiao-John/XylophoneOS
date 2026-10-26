# SPDX-License-Identifier: Apache-2.0
import json


with open("/work/py2/save.json", "r", encoding="utf-8") as stream:
    value = json.load(stream)
assert value == {"version": 2, "player": "雪", "items": ["lamp", "key"], "score": 42}
print("PY2_REBOOT_LOAD_OK", value["player"], value["score"])
