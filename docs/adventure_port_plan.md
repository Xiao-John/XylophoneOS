# Open Adventure 依赖内建计划：在 XOS 内生成 dungeon 数据并构建

2026-10-25，0034 规划。用户选定 Open Adventure（Colossal Cave），要求中文输出、
英文输入，并明确：**不是另写一个游戏，而是在 XOS 内实现 Open Adventure 缺少的
构建依赖**，让它在客体里完成“数据生成 + C 编译 + 运行”。本页只做计划，尚未
修改源码、未运行客体 gate。

## 目标与版本

- 冻结 **Open Adventure 1.12**（2023-02-06，Debian bookworm 同源）。已下载到
  `.cache/xos_seed/adventure/open-adventure-1.12.tar.gz`，SHA256
  `b6db9554157c87907dd2d90f0190217cc826faee5781765b6026ca5ce90235f2`。
- 许可证以包内 `COPYING` 为准：BSD 2-clause（Crowther/Woods/Raymond）。
- 目标链路：`adventure.yaml` + `make_dungeon.py` → `dungeon.c/h` → 与
  `main.c/init.c/actions.c/score.c/misc.c/saveresume.c` 一起编译 → 客体运行。
- 产物：静态 ELF `/out/advent`；中文叙述、英文命令；存档走 ASCII 路径。
- 不使用宿主预生成的 `dungeon.c/h` 或 `adventure.dat`；生成步骤必须在 XOS 内执行。

## 真实依赖清单（已对照 1.12 源）

| 依赖 | 现状 | 计划 |
|---|---|---|
| `make` | XOS 无 make | 不移植 make；提供显式文件列表的 `build.sh`，dash 可直接执行 |
| Python 3 | 已有 CPython 3.14.9 移植 | 复用 `/usr/bin/python3`；只装运行生成器所需的最小标准库 |
| `yaml`（PyYAML） | 无 | **在 port 内实现最小 `yaml.py` 子集**，见 D1 |
| `libedit/readline` | 无 | port-local `editline/readline.h` + `xos_readline.c`（`fgets` 实现；`add_history` 空操作） |
| `getopt/getopt_long` | libc 已有 | 直接用 |
| `time/localtime` | libc 有符号，XOS 无墙钟 | patch `srand(time(NULL))` 为固定种子；存档时间戳写 0 |
| `signal` | libc 有符号，无真实信号 | patch SIGINT 安装路径；交互 EOF/退出不依赖信号 |
| `isatty/gettimeofday` | libxos 有符号 | 用 `isatty` 区分交互/脚本；不依赖 `gettimeofday` |
| `curses/termios` | 未使用 | 不引入 |
| `-fstack-protector-all`/`_FORTIFY_SOURCE` | 目标 libc 不一定支持 | 构建脚本改用已验证的静态链接 flags，不照搬上游 Makefile |

## D1：最小 `yaml.py` 子集（首选方案）

`make_dungeon.py` 只 `import sys, yaml`，并调用 `yaml.safe_load(f)`；YAML 文件用到：

- `!!omap`（有序映射，PyYAML 返回 `(key, value)` 列表）
- 缩进式 map/sequence；`- key:` 形式
- flow sequence `[ROOT, WEST]` 和 flow map `{verbs: [...], action: [...]}`
- 单/双引号字符串、转义、`!!null`
- block scalar `|-`（多行消息）
- anchors `&name` / aliases `*name`（hints/locations 引用）

实现一个**只服务该冻结文件**的递归下降加载器，不做通用 YAML：
- 读取 UTF-8 文本，按缩进解析 map/sequence；
- 实现 `!!omap` 为有序对列表；
- alias 返回同一对象（PyYAML 语义）；
- 块标量按缩进收集，保留换行规则；
- 明确拒绝不支持的语法，不静默猜。

**验收 oracle**：宿主用 PyYAML 6.0.3 跑上游 `make_dungeon.py` 生成参考
`dungeon.c/h`；XOS 用我们的 `yaml.py` 跑同一脚本，产物必须**逐字节相同**。
若不能相同，先修 parser，不带差异进入编译。

备选 D1-C：若 Python 方案在客体过重或子集失控，改为 port-local C
`mkdungeon.c`，直接读 YAML 并写 `dungeon.c/h`；代码量更大，作为回退，不默认选。

## D2：构建脚本（替代 make）

客体 `/src/open-adventure` 下：

```sh
python3 make_dungeon.py
/usr/bin/x86_64-elf-gcc -std=c99 -D_DEFAULT_SOURCE -DVERSION=\"1.12\" \
  -O2 -static --sysroot=/sysroot -o /out/advent \
  main.c init.c actions.c score.c misc.c saveresume.c dungeon.c \
  xos_readline.c
```

- 显式文件列表；dash B1 关闭 glob，不依赖 `*.c`。
- 不加 `-fstack-protector-all`、`_FORTIFY_SOURCE`、libedit；这些不是游戏语义。
- 先 `-c` 分步编译便于定位，正式 gate 用一条链接命令。
- 构建失败必须保留 `dungeon.c/h` 和编译器输出，不静默重试。

## D3：中文输出、英文输入

- 翻译 `adventure.yaml` 的显示文本：`locations.description.*`、
  `objects.inventory/descriptions/changes`、`arbitrary_messages`、
  `classes.message`、`turn_thresholds.message`、`obituaries`、
  `hints.question/hint`、`actions.message`。
- **保留** `motions.words`、`actions.words`、`objects.words` 的英文词，parser 不变；
  输入仍是 `TAKE LAMP`、`GO NORTH`。
- `make_dungeon.py` 的文件读写显式加 `encoding="utf-8"`，避免 C locale 下编码漂移；
  C 字符串里的 UTF-8 字节原样输出。
- 检查 `%S`（英文复数）、`%d`/`%s` 插入；中文句子不需要复数时一并改文案。
- 80 列换行/中文显示宽度不匹配先记录为已知限制，不在首批做 wcwidth 排版。

## D4：运行适配

- 交互：`myreadline()` 走本地 `readline()`；提示 `> `；EOF 退出。
- 脚本：`advent /tmp/commands.txt` 走上游脚本路径，便于客体 gate。
- 存档：`saveresume.c` 的时间戳固定 0；`-r` 读档、`suspend` 写档；
  文件名提示仍可用本地 readline；测试用固定 `/tmp/adventure.sav`。
- `srand(1)` 固定，保证 gate 可复现；不把伪随机当安全随机。
- 不实现完整信号/终端控制；Ctrl-C 不由本批保证。

## 构建与冻结布局

```text
src/ports/adventure/
  source_lock.json          # 1.12 包、SHA256、来源、许可证
  upstream/                 # 原包 COPYING/NEWS 等只读材料
  patches/                  # D2/D4 最小补丁（UTF-8 open、seed、signal）
  xos/yaml.py               # D1 最小 YAML 子集
  include/editline/readline.h
  xos_readline.c
  build.sh                  # D2 显式构建
  adventure.yaml            # 翻译后的冻结数据（保留 upstream 副本对照）
tests/adventure_smoke.py
```

## 验收 gate

1. **G0 依赖探针**：宿主确认源文件清单、缺失符号、`yaml.py` 子集覆盖全部构造；
   客体确认 `python3` 能运行 `make_dungeon.py`（最小标准库）。
2. **G1 生成器等价**：宿主 PyYAML 参考 vs XOS `yaml.py` 产物 `dungeon.c/h`
   逐字节一致；记录 SHA256。
3. **G2 客体构建**：在 XOS 内执行 `python3 make_dungeon.py` 和 gcc 链接，产物 ELF
   可执行；禁止宿主预生成数据。
4. **G3 游戏 gate**：脚本输入 `look`、`go north`、`take lamp`、`inventory`、
   `save`、`quit`、重启 `-r`；中文输出逐字节核对；非法命令、缺存档、EOF 退出。
5. **G4 资源**：退出回 Xsh，任务/页回收；不覆盖日常盘/发布镜像；独立测试盘。

## 风险与应对

- YAML 子集遗漏（anchor/omap/块标量）：用全文件构造清单 + 字节级 oracle，失败即停。
- CPython 客体标准库不足：只装 `encodings/codecs/linecache` 等最小集合；仍缺则
  回退 D1-C。
- `isatty`/`readline` 行为差异：交互与脚本两条路径分别测。
- 时间/信号缺失：固定种子、零时间戳、去掉 SIGINT 依赖；不伪造真实时间。
- 中文宽度/换行：首批记录，不阻塞文本正确性。
- 上游 1.12 的 `main.c`/`saveresume.c` 可能还有未列出的 POSIX 调用：先交调用栈，
  再决定 shim，不扩公共 libc。

## 明确不做

- 不移植 make、完整 PyYAML、libedit、curses/termios；
- 不做运行时语言包、`LANG` 选择、安装器；
- 不改文件服务路径规则、不扩内核 ABI；
- 不保证完整 POSIX、信号、作业控制、中文排版；
- 不把宿主生成的 `dungeon.c/h` 当作 XOS 构建输入。

## 下一步（待用户确认）

推荐先做 **D1（最小 `yaml.py`）**：新增代码最少，且能保持上游生成器不变；
CPython 已是既有移植，构建盘只多一个解释器和少量标准库。若确认，下一步：
1. 冻结 1.12 到 `src/ports/adventure/`（source_lock、COPYING、upstream 副本）；
2. 实现 `yaml.py` 子集并用宿主 PyYAML 做字节 oracle；
3. 加 readline/time/signal/UTF-8 补丁与 `build.sh`；
4. 在客体跑 G1–G4。
