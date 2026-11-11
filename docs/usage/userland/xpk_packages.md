<!-- SPDX-License-Identifier: Apache-2.0 -->
# XPK 包化应用开发（宿主打包 + xypm 管理）

把独立应用打成 `.xpk`，再用 xypm 安装/查询/升级/移除。XPK 是有界、确定性的
ustar 归档：首个成员是 `manifest.json`，其余为 `payload/<路径>` 普通文件，不含
目录项、链接与执行代码；校验只做完整性与 ELF 布局检查，不是签名或运行授权。
参数以各脚本 `--help` 实测为准，下文为摘要。

| 角色 | 工具 | 位置 |
|---|---|---|
| 项目构建/打包（宿主） | `scripts/xos_app.py` | 仓库根执行 |
| 包容器与离线盘事务（宿主） | `scripts/xypm.py`、`scripts/xypm_format.py` | 仓库根执行 |
| 客体查询/事务 | `/usr/bin/xypm` | 工作盘上 |
| profile / schema | `config/package/*.json`、`app_v1.schema.json`、`xpk_v1.schema.json` | 仓库内 |

机制与字段语义见[包管理计划](../../plans/packages.md)；客体内写入事务见
[maintenance](../supervisor/maintenance.md)。

## 最小 xos_app.json 模板

不必手写：`xos_app.py init` 会生成（下例为 `--language cpp` 实测产物，
路径均为项目内相对路径）：

```json
{
  "format_version": 1,
  "id": "friends.hello_friend",
  "upstream_version": "0.1.0",
  "revision": 0,
  "target_profile": "xos-x86_64-static-single-v1",
  "language": "cpp",
  "sources": ["src/main.cpp"],
  "required_features": ["stdio", "cxx_runtime"],
  "runtime_dependencies": [],
  "files": [
    {"source": "build/hello_friend.elf", "path": "usr/bin/hello_friend", "role": "executable"},
    {"source": "LICENSE", "path": "usr/share/licenses/friends.hello_friend/LICENSE", "role": "data"},
    {"source": "src/main.cpp", "path": "usr/share/friends.hello_friend/source/main.cpp", "role": "data"}
  ],
  "licenses": ["usr/share/licenses/friends.hello_friend/LICENSE"]
}
```

| 字段 | 规则（`xos_app.py` / `xypm_format.py` 实测） |
|---|---|
| `id` / `target_profile` | 标识符：小写字母开头，含数字/`_`/`.`/`-`，≤80 字节 |
| `sources` | 1–128 个且不重复；后缀须与 `language`（`c` 或 `cpp`）一致；只能落在项目内 |
| `files` | 1–8000 项 `{source,path,role}`；`role` 只能是 `executable`/`data`；**恰有一个 executable，且 `source` 必须是 `build/` 直接子文件**（多程序预置树请改用 `xypm.py pack`） |
| `path` | 装载目标必须在 `/usr/bin`、`/usr/lib`、`/usr/share` 之下；`/usr/bin` 只能是直接文件名；ASCII 字母数字与 `_.+-`，禁止 `~`、尾随点/空格 |
| `required_features` | 必须是所选 profile `features` 的子集（如 `stdio`、`heap`、`file_io`、`directories`、`static_tls`、`cxx_runtime`；`stdio_transfer`、`spawn_delegate` 仅部分 profile 有） |
| `licenses` | 非空，且每条都是包内已存在的 `usr/share/...` 数据文件；打包时自动追加该 SDK 真实 `LICENSE`/`NOTICE`/`COPYING.NEWLIB` 与 `licenses/` 声明 |
| `runtime_dependencies` | 可空；非空时每项为 `{id,upstream_version,revision,sha256}` 精确匹配，无版本范围求解 |
| `revision` | 整数 `0 ≤ r < 2^31`；升级依赖按 id+版本+revision+包 SHA256 精确匹配 |

## 宿主打包命令

先有交叉工具链（`x86_64-elf-gcc/g++` 在 `PATH`，`-dumpmachine` 必须是
`x86_64-elf`、版本必须等于 profile 的 `compiler_version`，当前为 `16.2.0`；
`CPATH`/`LIBRARY_PATH` 等注入变量必须未设置）。项目放在仓库外的独立目录：

```sh
SDK="$PWD/build/releases/0.0.1-1024/xylophoneos_revival_0.0.1-1024_sdk"
PROJECT=./xos_hello_friend
python3 scripts/xos_app.py init "$PROJECT" --id friends.hello_friend --language cpp
python3 scripts/xos_app.py build "$PROJECT" --sdk "$SDK"
python3 scripts/xos_app.py check "$PROJECT" --sdk "$SDK"
python3 scripts/xos_app.py pack "$PROJECT" --sdk "$SDK" -o "$PROJECT/dist/hello_friend.xpk"
python3 scripts/xypm.py inspect "$PROJECT/dist/hello_friend.xpk"
python3 scripts/xypm.py verify "$PROJECT/dist/hello_friend.xpk" --profile config/package/xos_x86_64_static_single_v1.json
```

| 子命令 | argparse（实测 `--help`） | 说明 |
|---|---|---|
| `xos_app.py [--profile P] init` | `init --id ID [--language {c,cpp}] project` | 新建项目与模板；`project` 必须不存在 |
| `xos_app.py [--profile P] build` | `build --sdk SDK project` | 交叉编译到 `build/<name>.elf`，写 `build/build_receipt.json`（输入/编译器/SDK 树哈希/产物摘要） |
| `xos_app.py [--profile P] check` | `check --sdk SDK project` | 校验回执与当前源码、SDK、profile 一致 |
| `xos_app.py [--profile P] pack` | `pack --sdk SDK -o OUTPUT project` | `check` 通过后打成 `.xpk`，随即完整回读校验 |
| `xypm.py inspect` | `inspect package [--profile P] [--sha256 H]` | 打印 manifest；不带 `--profile` 只查格式/完整性 |
| `xypm.py verify` | `verify package [--profile P] [--sha256 H]` | 流式逐成员摘要 + 可执行文件 ELF 布局检查；输出 `status: verified_integrity_only` |

上面整串命令已在当前工作区实测通过（`init`→`build`→`check`→`pack`→
`inspect`→`verify` 退出 0）。要点：

- 输出文件已存在则拒绝覆盖（实测 `xos_app: [Errno 17] File exists: ...`）。
- 源码、SDK 或构建器任一变化后必须重新 `build`，否则 `check`/`pack` 拒绝；
  编译到临时文件再原子替换，失败不会让旧 ELF 冒充新产物。
- 回执状态写 `cross_built_guest_not_run` / `packed_guest_not_run`：只代表
  宿主构建与打包完成，**不代表已在客体运行**。

### profile 绑定规则（SDK 树哈希必须登记）

| 绑定点 | 规则 |
|---|---|
| 项目 → profile | `xos_app.json.target_profile` 必须等于 `--profile` 文件的 `id` |
| SDK → profile | 该 SDK 目录整棵树的 SHA-256（无符号链接、逐文件摘要的 canonical 摘要）必须出现在 profile 的 `sdk_tree_sha256` 数组里；未登记直接拒绝：`xos_app: SDK snapshot not registered for profile; do not mix headers/libraries`（实测） |
| features → profile | `required_features ⊆ features`，否则 `required feature unavailable` |
| 包 → 盘上数据库 | 客体/宿主事务都要求包的 `target_profile` == 数据库 `target_profile` == xypm 自身编译时的 profile；不符报 `package target profile differs from this xypm build` / `installed database profile mismatch`（源码 `xypm_native.hpp`、`xypm.cpp`） |

profile 文件在 `config/package/`，常用三个：

| 文件 | `id` | `sdk_tree_sha256` 条数 | 备注 |
|---|---|---|---|
| `xos_x86_64_static_single_v1.json` | `xos-x86_64-static-single-v1` | 1 | `xos_app.py`/`xypm.py` 缺省 profile；登记的正是发行 SDK `0.0.1-1024`（实测其树哈希与登记值一致） |
| `xos_x86_64_static_single_b2_v1.json` | `xos-x86_64-static-single-b2-v1` | 4 | 冻结单线程 B2 运行库 + C++ 归档；**发行工作盘数据库用的就是它**（实测 `db.json` 的 `target_profile`） |
| `xos_x86_64_daily_c3_candidate_v1.json` | `xos-x86_64-daily-c3-candidate-v1` | 2 | 候选 profile，仅记录已跑过的受限命令链，不是发行冻结 profile |

`verified_system_builds` 是该 profile 认可的系统构建 ID 列表；`features`、
`sdk_tree_sha256`、`verified_system_builds`、`scope`、`evidence` 的语义以
profile 文件本身与 [packages 计划](../../plans/packages.md)为准。**换 SDK 或
换 profile 前先确认树哈希已登记；新 SDK 需要新增 profile 回执，不能自填字段。**
`scripts/prepare_xypm_sdk.py` 展示了 B2 组合 SDK 的冻结方式（只接受与资格
输入完全一致的树哈希，不匹配即失败），能否复用以该脚本 `--help` 与实际回执为准。

安装到 0.0.2-1103 发行盘时，用 b2 profile 绑定当前 SDK 树：

```sh
python3 tools/adopt_sdk.py --base-profile config/package/xos_x86_64_static_single_b2_v1.json -o ../xos_sdk_b2.json
```

不要用 `xos-x86_64-sdk-local` 安装到该盘；事务会拒绝并提示 b2 配置。local profile
仅用于开发/宿主自测。

### 复杂包与工具包

- 预置 stage 树（多程序、非模板结构）：`xypm.py pack --root <stage>
  --manifest <manifest.json> -o <out.xpk> [--profile P]`。
- 日常工具包实例：`src/ports/sbase/daily_utilities.json`（`format_version`/
  `scope`/`tools[]`，每项 `name`、`source`、`license`、`scope`、`guest_path`）
  由 `scripts/build_daily_utilities.py` 构建，再用
  `scripts/package_daily_utilities.py --tools <dir> --sdk <sdk> --profile <p> -o <out.xpk>`
  打包；回执要点见 [0069](../../work_log/0069_daily_utilities.md)。
- xypm 自身就是这样一个包（`scripts/build_xypm.py --sdk <sdk> [--profile P]
  [--fault-injection]`，产物 `xos.xypm`）。

## 客体安装与查询

### 先把 .xpk 放进工作盘

关闭使用该盘的 QEMU 后：

```sh
python3 scripts/work_disk.py work_disk.img import /out/hello_friend.xpk \
  /path/to/hello_friend.xpk
```

`import` 不覆盖已有路径（报 `FatFs error=8`）。`make disk` 的空盘没有
`/out`，先 `mkdir`；发行盘已有 `/out`。

### 三种入口

| 场景 | 命令 | 依据 |
|---|---|---|
| 只读查询（任意时刻） | `xypm list`、`xypm info <id>`、`xypm verify <file.xpk> [sha256]`、`xypm plan install\|upgrade <file.xpk>`、`xypm plan remove <id>`、`xypm --help`、`xypm --version` | `src/user/programs/xypm.cpp`；`tests/package_p1_guest.py` 实测 |
| 写入事务（安装/升级/卸载） | `maint-run /usr/bin/xypm install /out/hello_friend.xpk [--sha256 <digest>]`、`maint-run /usr/bin/xypm upgrade /out/hello_friend.xpk [--sha256 <digest>]`、`maint-run /usr/bin/xypm remove friends.hello_friend` | `docs/usage/supervisor/maintenance.md`；`tests/package_p2_transactions.py`、`tests/daily_utilities_p2_guest.py` 实测 |
| 事务中断后的恢复 | `maint-recover-boot`（内置恢复器），或 `maint-recover /usr/bin/xypm recover` | `tests/package_p2_faults.py`、`tests/package_p2_self_upgrade.py` 实测 |

- `maint-run` 是 Xsh 内建，要求当前只有监督任务与 files 服务存活（有后台或
  构造中的应用会返回 busy）；**在 dash 里不能执行维护入口**，先 `exit` 回
  `xsh>`。
- 成功输出 `maintenance: completed`；非零/异常/取消会 `maintenance: retained`
  并保持准入屏障，必须恢复成功才重新开放普通写入。
- 退出码（`xypm --help` 与实测）：成功 0；包未安装（`info` 不存在 id）1；
  不支持的命令/参数 2（`xypm: unsupported command or arguments; use --help`）；
  包损坏/摘要不符/计划被拒 3。
- 查询也可在 dash 下执行同一程序：`dash /tests/list.sh`（脚本里写
  `xypm list`），`tests/package_p1_guest.py` 实测 xsh 与 dash 结果一致。

### 也可在宿主离线事务（不开 QEMU）

```sh
python3 scripts/xypm.py install hello_friend.xpk \
  --image work_disk.img --output-image installed.img --offline \
  --profile config/package/xos_x86_64_static_single_v1.json
python3 scripts/xypm.py list --image installed.img
python3 scripts/xypm.py info friends.hello_friend --image installed.img
python3 scripts/xypm.py verify-installed --image installed.img
python3 scripts/xypm.py upgrade newer.xpk --image installed.img \
  --output-image upgraded.img --offline --profile <同上>
python3 scripts/xypm.py remove friends.hello_friend --image upgraded.img \
  --output-image removed.img --offline --profile <同上>
```

`install/upgrade/remove` 的 `--offline` 是必填标志（argparse `required=True`），
并强制 `--output-image` 新文件：源盘只读复制、全会话排他，事务在私有候选盘
完成并回读验证后才发布；不替换日常工作盘、不重启 QEMU。安装/升级可追加
`--sha256 <整包摘要>`。实测 `install` 返回 `status: exported_candidate`、
`verified_files`、`mutations`，源盘摘要不变。数据盘上限：64 包 / 8192 归属
文件 / 数据库 1 MiB；数据库在 `/var/lib/xypm/db.json`，只读投影 `index.tsv`。

### 实例与既有产物

| 实例 | 位置 |
|---|---|
| hello xpk（P0/P1 门禁） | `build/package_p0/hello_c.xpk`、`hello_cpp.xpk`；`build/package_p1/` |
| 日常工具候选包 | `build/daily_utils_002.xpk` 等；profile `config/package/xos_x86_64_daily_c3_candidate_v1.json` |
| 发行盘已装包 | 发行 `work_disk.img` 实测含 `/usr/bin/xypm`、`/usr/bin/x86_64-elf-gcc`、`/sysroot`、`/var/lib/xypm/db.json`（profile `xos-x86_64-static-single-b2-v1`，已装 `python_idna`），**不含** `/usr/bin/dash` |

## 常见错误

| 现象 | 原因与处理 |
|---|---|
| `SDK snapshot not registered for profile; do not mix headers/libraries` | SDK 树哈希未登记进所选 profile；换回 profile 登记的冻结 SDK，或新增 profile 回执 |
| `compiler target/version mismatch` | `x86_64-elf-gcc` 的 target/版本与 profile `compiler_version` 不符；以 profile 与 `--help` 为准 |
| `required feature unavailable` | `required_features` 超出该 profile `features` |
| `File exists` | `pack`/`--output-image` 拒绝覆盖；换新输出名 |
| `builder changed; rebuild before packing` / `project inputs changed` | 构建器或源码变了；重新 `build` |
| `package already installed; choose install` / `package is not installed; choose upgrade` | install/upgrade 与库状态不一致；先 `xypm info <id>` 确认 |
| `installed database profile mismatch` / `package target profile differs from this xypm build` | 包、数据库、xypm 二进制三者 profile 不一致；发行盘用 `xos-x86_64-static-single-b2-v1` |
| `busy or denied error=-11`、`maintenance: retained` | 有后台/构造中应用，或事务失败未恢复；退出其他程序再 `maint-run`，必要时 `maint-recover-boot` |
| `FatFs error=8` | `import` 目标已存在；换文件名或新盘副本 |
| 客体里没有 `xypm` | `make disk` 的空盘不含 xypm；需宿主离线安装 `xos.xypm` 包，或使用发行工作盘 |

## 相关

- [getting_started（宿主 compile.py 主路径）](getting_started.md)
- [in_guest_build（客体内编译）](in_guest_build.md)、[dash](dash.md)
- 命令：[maintenance](../supervisor/maintenance.md)、[exec-file](../supervisor/exec-file.md)、
  [sync](../supervisor/sync.md)
- 机制：[包管理计划](../../plans/packages.md)、[E08](../../e08.md)、
  [E04 装载与 SDK 契约](../../e04_loader_sdk.md)
- 索引：[命令使用手册](../index.md)
