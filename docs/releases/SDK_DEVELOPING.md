<!-- SPDX-License-Identifier: Apache-2.0 -->
# XOS SDK 开发者指南（随 SDK 分发）

本目录是**开箱可用的用户态开发包**：交叉编译 ELF、打 XPK 包、查文档。
需要 `x86_64-elf-g++`（16.2.0）在 `PATH`；宿主 Python 3.10+。

## 目录导览

| 路径 | 用途 |
|---|---|
| `compile.py` | 一键编译静态 C/C++ ELF（最短路径） |
| `examples/hello.c` `hello.cpp` | 最小示例源码 |
| `examples/xpk_hello/` | 最小 XPK 工程（`xos_app.json` + 源码） |
| `tools/xos_app.py` | XPK：init / build / check / pack |
| `tools/xypm.py` | XPK：inspect / verify |
| `tools/adopt_sdk.py` | 把**本 SDK 树哈希**写入本地 profile（XPK 前必跑一次） |
| `config/package/*.json` | 预置 profile（发行绑定）；本地用 `adopt_sdk.py` 生成的 profile |
| `docs/usage/` | 命令与开发手册（含 XPK、dash、Python、Qt 边界） |
| `docs/releases/playbook.md` | 发版流程（维护者向） |
| `include/` `lib/` `cpp/` | 头文件与静态库（含 C++ 运行库） |
| `DEVELOPING.md` | 本文件 |

## 1. 三十秒：编译并跑通 hello

```sh
SDK=/path/to/xylophoneos_revival_0.0.2-1103_sdk
python3 "$SDK/compile.py" --c "$SDK/examples/hello.c" -o hello.elf
python3 "$SDK/compile.py" "$SDK/examples/hello.cpp" -o hello_cpp.elf
```

导入工作盘并在 `xsh>` 运行（工作盘与 QEMU 入口见 `docs/usage/userland/getting_started.md`）：

```text
xsh> exec-file /out/hello.elf
Hello from XOS C!
```

## 2. XPK 包化应用（推荐交付形态）

```sh
SDK=/path/to/..._sdk
# 一次性：生成绑定当前 SDK 树的 profile（写到 SDK 外，避免改变树哈希）
python3 "$SDK/tools/adopt_sdk.py" -o "$PWD/xos_sdk_profile.json"
PROFILE="$PWD/xos_sdk_profile.json"

python3 "$SDK/tools/xos_app.py" --profile "$PROFILE" init /tmp/demo --id demo.hello --language cpp
python3 "$SDK/tools/xos_app.py" --profile "$PROFILE" build /tmp/demo --sdk "$SDK"
python3 "$SDK/tools/xos_app.py" --profile "$PROFILE" check /tmp/demo --sdk "$SDK"
python3 "$SDK/tools/xos_app.py" --profile "$PROFILE" pack /tmp/demo --sdk "$SDK" -o /tmp/demo/hello.xpk
python3 "$SDK/tools/xypm.py" inspect /tmp/demo/hello.xpk
```

客体安装与查询（`xsh>`）：

```text
maint-run /usr/bin/xypm install /out/hello.xpk
xypm info demo.hello
```

字段规则、profile 绑定与维护事务：`docs/usage/userland/xpk_packages.md`。

也可从示例工程起步：复制 `examples/xpk_hello` 后改 `id`/源码，再执行 build/check/pack
（`target_profile` 须等于你所用 profile 的 `id`，`adopt_sdk.py` 默认写 `xos-x86_64-sdk-local`）。

## 3. dash 与客体 Python

- dash：安装 ISO 首启装入 `/usr/bin/dash`；`xsh>` 下 `dash /out/script.sh`。
  能力边界见 `docs/usage/userland/dash.md`。
- Python：`python3 /out/script.py`；有 zlib/SQLite/线程，**无 GUI、无 pip**。
  见 `docs/usage/userland/python.md`。

## 4. 图形界面

- **客体内无 Qt**；宿主用发行 `qt6_static` 资产交叉编译，见
  `docs/usage/userland/qt_development.md` 与 `src/ports/qt6/REDISTRIBUTION.md`（仓库）。
- 原生显示：`gfxdemo` / display service（见 `docs/state.md` 能力表）。

## 5. 常见失败

| 现象 | 处置 |
|---|---|
| `SDK snapshot not registered for profile` | 先跑 `tools/adopt_sdk.py`，并用生成的 `--profile` |
| `compiler target/version mismatch` | 需 `x86_64-elf-g++` 16.2.0；勿设 `CPATH`/`LIBRARY_PATH` |
| `CPPFLAGS`/环境注入被拒 | 卸掉宿主交叉污染变量 |
| `FatFs error=8`（重复 import） | 工作盘 import 不覆盖，先换名或清目标 |

## 许可

SDK 内 `LICENSE`/`NOTICE`/`licenses/`/`third_party_notices/` 随包携带；
Qt 静态库在独立发行资产，条款见该资产内 `licenses/` 与仓库 `REDISTRIBUTION.md`。
