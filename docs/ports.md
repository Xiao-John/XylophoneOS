# 端口规范（port.json v1）

2026-11-12。本文件是 `src/ports/` 下**带 `port.json` 的目录**的权威规范；校验入口
`python3 scripts/ports.py check`。许可登记见第 8 节，目录总览见 [src/ports/README.md](../src/ports/README.md)。

本规范只描述**元数据、构建配方与证据**，不引入内核/ABI 面。端口默认只在客体侧交付：
产物打成 `.xpk`，由 xypm 安装；不进内核、不进启动镜像清单。需要改
`src/kernel`、`src/user`、`src/shared` 的端口不是本规范的适用范围，必须先按宪法走
ABI/契约流程，端口侧只记录依赖。

## 1. 目录契约

```text
src/ports/<id>/
  port.json            # 必需；本规范的唯一入口
  README.md            # 必需；四节：状态 / 构建 / 安装与验证 / 已知限制
  source_lock.json     # source 非 null 时必需；按 kind 校验
  build.py|build.sh    # status ≥ cross_built_guest_not_run 时必需
  patches/             # 可空；NNNN_topic.patch
  upstream/            # 可选；仅存许可/声明材料，不存整包源码
```

`<id>` 与 `port.json.id` 一致：小写字母开头，只含 `a-z0-9_`（建议 snake_case），≤64 字节。
`_` 开头目录是模板或草稿，校验器跳过。

上游归档不入 git：放 `.cache/xos_seed/` 或仓库外目录，由环境变量传给配方。

## 2. `port.json` 字段

| 字段 | 类型 | 规则 |
|---|---|---|
| `format_version` | int | 必须是 `1` |
| `id` | string | 见第 1 节；全仓唯一 |
| `name` | string | 人类可读名，1–120 字节 |
| `upstream_version` | string | 上游版本，1–128 字节 |
| `license` | string[] | 1–16 项，SPDX 标识（无法确定时写 `NOASSERTION` 并在 `note` 说明） |
| `homepage` | string \| null | `https://` 开头或 null |
| `source` | object \| null | `null` 表示 XOS 自研；否则见第 3 节 |
| `build.system` | string | `autotools` / `make` / `cmake` / `meson` / `custom` / `prebuilt` |
| `build.recipe` | string \| null | 相对端口目录的脚本路径；status ≥ `cross_built_guest_not_run` 时必需 |
| `build.patches` | string[] | 相对路径，必须都在 `patches/` 且存在 |
| `package.id` | string | 包标识，与端口 id **不同**：小写字母开头，可含 `.`/`-` 分隔（如 `thirdparty.nasm`），≤80 字节；全仓唯一，与 `package.target_profile` 绑定 |
| `package.target_profile` | string | 必须等于 `config/package/*.json` 里某个 `id` |
| `package.xpk_sha256` | string \| null | 64 位小写十六进制；status ≥ `packed_guest_not_run` 时必需 |
| `integration.guest_only` | bool | 端口默认 `true` |
| `integration.bootstrap_images` | string[] | `guest_only` 时必须为空 |
| `integration.iso_members` | string[] | `guest_only` 时必须为空 |
| `status` | string | 见第 5 节枚举 |
| `note` | string | 1–512 字节；`blocked` 时必须写明阻塞项 |
| `evidence` | string[] | 仓库相对路径；必须存在；见第 7 节 |

未知字段直接判失败：字段只能按本表增加，不能就地扩展。

## 3. `source` 与 `source_lock.json`

`source` 非 null 时形如：

```json
{"kind": "tarball", "lock": "source_lock.json"}
```

`lock` 是相对端口目录的路径，默认 `source_lock.json`。按下表校验锁文件；三种 `kind`
互不兼容，不允许混写：

| kind | 必需字段 | 说明 |
|---|---|---|
| `tarball` | `version`、`url`、`sha256`、`archive` | 单归档；`archive` 是文件名，哈希针对归档字节 |
| `git` | `repository`、`commit`（40 位）、`tree`、`files[]`（`path`+`sha256`） | 逐文件锁定；`files` 可空表示只锁提交 |
| `component_set` | `components[]`，每项 `name`、`version`、`url`、`sha256`、`license` | 多组件组合（如静态库闭包） |

哈希来源必须可复核：若只从镜像取得而未与上游发布页比对，在锁文件加
`"sha256_scope": "mirror_fetch"` 并在 `README.md` 的“已知限制”里写明。`kind` 允许
附加字段（如 `mirror`、`upstream_tag`、`release_page`），校验器只校验必需字段的类型。

## 4. 补丁

- 文件名 `NNNN_<slug>.patch`，四位十进制序号，从 `0001` 起连续；必须被
  `build.patches` 列出，且 `patches/` 内不得有未列出的 `.patch`。
- 一律 `git format-patch` 格式：首行 `From <40 位 commit>`，含 `Subject:` 头。
- 补丁只改上游文件；XOS 侧粘合代码放端口自己的 `build.py` 或独立源文件，不进补丁。
- 禁止二进制补丁、文件改名、权限位修改；确需改名的在 `README.md` 记录理由。
  校验器会拒绝含 `GIT binary patch`、`Binary files`、`old mode`/`new mode`、
  `rename from`/`rename to` 的补丁。

## 5. 状态与升级条件

| status | 含义 | 升级条件 |
|---|---|---|
| `planned` | 只有元数据 | 锁文件通过 `source_locked` |
| `source_locked` | 上游来源与哈希已锁定 | 配方跑出 ELF/构建回执 |
| `cross_built_guest_not_run` | 宿主交叉构建通过 | 打成 `.xpk` 且 `xypm.py verify` 通过 |
| `packed_guest_not_run` | 包完整性与 profile 检查通过 | 客体里实际运行并落证据 |
| `guest_verified` | 客体验证通过 | —（后续变更需重验，见第 7 节） |
| `blocked` | 有明确阻塞 | 阻塞解除后回到对应状态，`note` 写清原因 |
| `retired` | 停止维护 | — |

状态词只此八个，不得新造同义词。`source_locked` 及之后的状态要求 `source` 非
null（自研、无上游来源的端口最多停在 `planned`）。

## 6. 构建配方契约

配方由环境变量驱动，**必须离线**（不下载、不访问网络），输入缺失即失败：

| 变量 | 必需性 | 含义 |
|---|---|---|
| `XOS_SDK` | 必需 | 解包后的冻结 SDK 根目录 |
| `XOS_SOURCE_ARCHIVE` | `kind: tarball` 时必需 | 本地归档路径，配方先核对 `sha256` |
| `XOS_SOURCE_GIT` | `kind: git` 时必需 | 本地 checkout，配方先核对 commit |
| `XOS_OUT` | 必需 | 输出目录，配方自行创建 |

输出固定为 `<XOS_OUT>/<package.id>-<upstream_version>.xpk` 与
`<XOS_OUT>/build_receipt.json`。`build_receipt.json` 至少记录：配方摘要、SDK 标识
（`manifest.json.build_id` 与树哈希）、编译器版本、输入哈希、产物哈希、`status`。
配方成功退出码 0；失败不得留下可误认为成功的旧产物。

## 7. 证据

- 路径相对仓库根，必须存在，可以是 `docs/reports/<port>_<date>/README.md`。
- `cross_built_guest_not_run` 起：至少一份构建证据含配方与产物哈希。
- `guest_verified`：证据必须含客体命令、原始输出、产物字节/哈希与系统 build id；
  只写“已通过”不算证据。本规范不要求把二进制入库，但哈希必须可追溯到具体构建输入。
- 证据是对冻结输入的陈述：换 SDK、换上游版本或改补丁后，状态退回
  `source_locked` 并重跑，不得沿用旧证据。

## 8. 许可登记

端口的许可分两层，不要混为一谈：

1. **包内文本**（所有端口）：`.xpk` 必须携带上游许可原文，manifest 的 `licenses`
   指向包内 `usr/share/licenses/<package.id>/` 下的数据文件。这一步由配方完成，
   不需要改仓库配置。
2. **发行物登记**（仅当端口产物随发行物分发）：产物进 ISO、SDK 或发行工作盘时，
   必须在 `licenses/components.json` 增加条目，字段沿用现有条目：
   `name`、`version`、`path`、`source`、`license`、`notices`、`used_in`、
   `modifications`、`artifact_sha256`（登记的哈希必须与仓库内实际文件一致）；
   未闭合的义务在 `licenses/open_items.json` 登记，并保证 `scripts/license_audit.py`
   通过。只是本地验证、未随发行物分发的 guest-only 端口不登记组件，也不伪造
   “已审”状态。

修改第三方代码时保留原条款并在 `modifications` 描述改动；XOS 侧粘合代码用自己的
许可（Apache-2.0），补丁不改变上游文件的历史归属。

## 9. 校验

```sh
python3 scripts/ports.py check src/ports/nasm     # 单个
python3 scripts/ports.py check --all              # 全部带 port.json 的目录
python3 scripts/ports.py check --all --json        # 机器可读
```

失败时退出码 1，逐条打印 `path: 错误`。校验器只做结构与一致性检查，不构建、不联网、
不执行端口配方。

## 10. 迁移

`src/ports/` 下不带 `port.json` 的目录（`adventure`、`aurora_browser`、`aurora_desktop`、
`binutils`、`browser_http`、`cpython`、`dash`、`gcc`、`make`、`ncurses`、`newlib`、
`qt6`、`sbase`）仍按各自 README 与 `source_lock.json` 的历史格式维护，**不受本规范约束**；
它们迁到 `port.json` 时按下表登记，不批量改写旧锁文件：

| 旧目录 | 迁移状态 |
|---|---|
| `nasm`（本规范首个样例） | 已迁移：`port.json` + `source_lock.json` + 配方 + 客体证据 |

新增端口一律按本规范建立，不得以“和某个旧端口一样”为由跳过 `port.json`。

## 11. 样例

[`src/ports/nasm/`](../src/ports/nasm/) 是首个完整样例：零源码补丁、autotools、
guest-only、`.xpk` 由 xypm 安装、客体实测汇编产物字节，证据在
[`docs/reports/nasm_2_16_03_20261112/`](reports/nasm_2_16_03_20261112/README.md)。
