# 0034：Open Adventure 在 XOS 内构建（D1）

2026-10-25。用户选定 Open Adventure，要求中文输出、英文输入，并在 XOS 内实现
其构建依赖。本组冻结 1.12，新增 port、最小 `yaml.py`、readline 适配和客体构建
脚本；没有改内核、文件服务、CPython 源码或共享发布镜像。

## 版本与冻结

- Open Adventure 1.12（2023-02-06），包
  `.cache/xos_seed/adventure/open-adventure-1.12.tar.gz`，SHA256
  `b6db9554157c87907dd2d90f0190217cc826faee5781765b6026ca5ce90235f2`。
- 许可证 BSD-2-Clause，`src/ports/adventure/upstream/COPYING`。
- 生成数据由 `adventure.yaml` 产生，不在宿主预生成。

## 实现的依赖

1. **PyYAML 子集** `src/ports/adventure/xos/yaml.py`：支持 `!!omap`、缩进
   map/sequence、flow `[]/{}`、单双引号、`!!null`、`|-` 块标量、anchor/alias；
   不支持的一律报错。对冻结 `adventure.yaml` 与 PyYAML 6.0.3 做深度比较，0 差异；
   生成器输出与 PyYAML 参考逐字节相同。
2. **readline/libedit**：`xos_readline.cpp` 用 SDK 控制台读实现 `readline()` /
   `add_history()`，`include/editline/readline.h` 提供声明；不引入 libedit。
3. **make**：不移植；`build.sh` 用显式文件列表和原生
   `/usr/bin/x86_64-elf-gcc/g++` 构建，dash 可直接执行（B1 无 glob）。
4. **时间/信号**：`srand(1)`、存档时间戳 0、去掉 SIGINT 安装；`VERSION` 在
   `advent.h` 给默认值，避免 shell 引号依赖。
5. **CPython 依赖**：复用既有 `/usr/bin/python3` 移植；构建盘只装最小标准库
   `encodings/codecs/linecache/os/posixpath/genericpath/stat/abc/_collections_abc/warnings`。

## 修改文件

- 新增 `src/ports/adventure/`：README、source_lock、patches、adventure.yaml
  中文子集、xos/yaml.py、xos_readline.cpp、include/editline/readline.h、build.sh。
- 新增 `tests/adventure_smoke.py`；计划与状态文档。
- 不改 CPython、libc、内核、dash 源码。

## 证据

系统 build `3d7665a665df9443`，镜像 SHA256
`74b07888492ed1c4c7b2117fcb42568d77a5523715df5375af7e86bfb7842b12`。
`build/adventure_report.json` 4/4：

- 客体 dash 执行 `/src/open-adventure/build.sh`，退出 0；脚本内部：
  `python3 make_dungeon.py` → `dungeon.c/h` → 原生 g++ 编译 readline shim →
  原生 gcc 链接 `/out/advent`。
- 客体生成 `dungeon.c` SHA256
  `9a2081708f06651a79fc67119f20d29598c79b4999017b0e3b4840a1f97e874c`，
  `dungeon.h` `d3d7553b...`，与宿主 PyYAML 参考逐字节一致。
- `/out/advent` 在客体运行，中文输出通过：欢迎语、起点长描述、退出确认、
  得分/等级文本；英文命令 `no/look/quit/yes` 正常。

## 中文范围与未完成

本批只翻译了启动、起点房间、得分/等级和灯/钥匙/宝箱/金币的名称与描述；其余
房间和消息仍是英文，不能称为完整中文化。未验收：

- `suspend`/`resume` 存档、重启读档；
- 脚本文件输入、完整 walkthrough、死亡/提示/矮人；
- 中文显示宽度与 80 列换行；
- 更完整的 YAML 子集和 D1-C C 生成器回退。

## 下一步

1. 扩充翻译并保留英文命令词；每次重新生成并核对 `dungeon.c/h` 哈希。
2. 加存档/读档与脚本输入 gate；再考虑完整流程。
3. 若 CPython 构建盘过重，评估 D1-C 的 C `mkdungeon`，不覆盖本实现。
