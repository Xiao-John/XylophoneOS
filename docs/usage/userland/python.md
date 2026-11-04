<!-- SPDX-License-Identifier: Apache-2.0 -->
# 客体 Python 开发（边界与用法）

XOS 发行盘自带 **静态 CPython 3.14**（`/usr/bin/python3`）。定位是
**脚本/数据/测试语言**，不是 GUI 语言。

## 能做什么（已验）

| 能力 | 说明 |
|---|---|
| 基础运行 | `python3 /out/script.py`；stdlib 齐（580 个 .py 随发行） |
| 线程/压缩/JSON | `threading`、`zlib`/`gzip`/`zipfile`、`json`（release_smoke `python_py3`） |
| 哈希/XML/路径 | hash/HMAC、pathlib、argparse、dataclasses、tomllib、Decimal、XML（PY3 A1） |
| SQLite | 3.54.1 静态 + XOS VFS（事务/约束/损坏恢复，PY3 B3） |
| 时区 | TZ + ZoneInfo/tzdata（PY3 B2） |
| 离线装小包 | 受限离线包/固定依赖安装（PY3 A2）；**不是在线 pip** |
| idna 等 wheel | 发行盘经 xypm 装入的纯 Python wheel（如 `python_idna`） |

## 不能做什么

- **无 GUI**：无 tkinter 后端、无 PyQt/PyGame；不能用 Python 画窗。
- **无 pip/ensurepip**：不能 `pip install`；只有受限离线安装路径。
- 无网络栈上的通用 HTTP 客户端资格（网络线 BLOCKED，见 `docs/state.md`）。

## 最小示例

```python
# /out/hello.py — 在 xsh> 下执行：python3 /out/hello.py
import json, zlib
print("py-ok", json.dumps({"x": 1}), len(zlib.compress(b"XOS")))
```

写文件、导入：宿主侧用 `python3 scripts/work_disk.py <image> import /out/hello.py hello.py`
（见 [getting_started](getting_started.md)）；或客体内 `edit` 后保存。

## 相关

- 资格细节：`docs/history/userland.md`（PY0–PY3、A/B 专项）
- 发行装配：idna 走 wheel、stage 须含 zlib（`docs/work_log/0203_release_packaging.md`）
- 包管理：[XPK 包化](xpk_packages.md)（若已建）；`xypm info python_idna` 类查询
