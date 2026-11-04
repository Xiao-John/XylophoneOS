# GCC 运行库逐成员 → 源码许可映射

2026-11-03 · 分支 `codex/d7_license_release_prep` · D7 许可面收口的一叶（另见
[GNU Seed 分发审查](../gnu_seed_distribution_20261103/)的 O5/R2、
[newlib 成员许可映射](../newlib_member_license_20261103/)）。
本目录只含本叶产物：`README.md`、`findings.json`、`manifest.json`（平铺根清单，
按 [evidence_integrity](../../../contracts/evidence_integrity.md) 契约）。

**性质与边界**：成员 → 源文件 → 声明类别的**映射与声明提取**，不是逐成员法律意见，
不授予任何发行资格；`scripts/license_audit.py` 的通过只是材料一致性检查。

## 1. 方法（五级解析，逐级递进，不猜）

脚本 `scripts/gcc_runtime_member_license_map.py`，复算命令：

```sh
cd "${XOS_XOS_ROOT}"
python3 scripts/gcc_runtime_member_license_map.py --out docs/reports/gcc_runtime_member_license_20261103/findings.json
python3 tests/report_manifest_check.py    # 本目录应出现在 compliant 列表
```

| 层级 | 依据 | 命中 |
|---|---|---|
| `dependency_file` | 构建树 `.deps/*.Po|*.Plo` 记录的编译源 | 4 |
| `build_log` | 构建日志里的真实编译命令行（含 `ln -s <全路径>` 行解析出的相对源名） | 240 |
| `build_log_libtool_alias` | libtool 同源多对象 `ltN-*` 别名回查 | 7 |
| `exact_stem` / `stem_text_search` | 源树同名文件 / 词干文本反查（按目标架构过滤 `config/<非 i386|x86_64>/`，优先实现文件、优先 `libgcc/` 与 `libstdc++-v3/`） | 82 / 12 |
| `symbol_lookup` | `x86_64-elf-nm` 取成员定义符号 → `c++filt` 反签名 → 源树唯一定位 | 52 |

解析源码根：`.cache/xos_seed/gcc/source/gcc-16.2.0`（含 in-tree 的 gmp/mpfr/mpc）。

## 2. 结果

| 归档 | 成员 | 已解析 | 未解析 |
|---|---|---|---|
| `libgcc.a` | 147 | 140 | 7 |
| `libstdc++.a` | 196 | 193 | 3 |
| `libsupc++.a` | 64 | 64 | 0 |
| **合计** | **407** | **397（97.5%）** | **10** |

**声明类别分布**（提取自已解析源文件，非法务归类）：

| 类别 | 成员数 | 说明 |
|---|---|---|
| `gcc_runtime_exception` | 314 | 文件含 "GCC Runtime Library Exception" |
| `gpl` | 23 | GPL 文本（工具链侧文件） |
| `other_copyright` | 55 | 仅版权行，无许可正文 |
| `no_declaration` | 5 | 文件内未见版权/许可声明 |
| `lgpl` / `dual_gmp` | 0 | 本批成员的源文件未命中该类文本（GMP/MPFR/MPC 为构建依赖，不在三份归档的成员里） |

**未解析 10 个（全部列出，不猜）**：`__main.o`、`_clz.o`、`_ctors.o`、
`_divmodbitint4.o`、`_mulbitint3.o`、`enable-execute-stack.o`、`floatunsitf.o`
（libgcc 7 个）、`basic_file.o`、`collate_members_cow.o`、`messages_members_cow.o`
（libstdc++ 3 个）。根因分三类：① libgcc 侧**没有保留编译日志/依赖记录**，同名或多候选
（如 `libgcc/libgcc2.c` vs `libgcc/soft-fp/*.c`、`config/locale/*` 多实现）无法唯一化；
② 目标架构过滤后仍剩 ≥2 个同级候选；③ 符号反查命中 >1 且无法进一步收窄。
完整候选清单见 `findings.json` 的 `unmapped`。

## 3. 与许可文本的对应

- **314** 个成员的源文件声明命中 GCC Runtime Library Exception —— 对应
  `src/ports/gcc/upstream/GCC-COPYING.RUNTIME`（随 1026 起随包携带，见
  [GNU Seed 分发审查](../gnu_seed_distribution_20261103/)的 O3）。
- **23** 个 GPL 命中对应 `GCC-COPYING3` / `GCC-COPYING`。
- 其余为版权/无声明，条款以文件内声明与上游 COPYING 为准。
- 三份归档本身**未做字节级逐成员溯源**（构建对象与分发归档的字节一致性只抽查过
  `ctype_members.o` 等样本，未全量核对）。

## 4. 局限（必须随数字一起读）

1. 本映射把**归档成员名**与**构建记录/符号**对回源文件；它不证明该源文件的法律条款，
   也不证明分发归档与某次构建对象逐字节相同。
2. 10 个未解析成员**没有**任何归属结论，不得默认为 "已审"。
3. 未做反汇编验证、未做依赖闭包展开（GMP/MPFR/MPC 作为构建依赖的静态并入仍按
   [GNU Seed 分发审查](../gnu_seed_distribution_20261103/)的 R6 记为推断）。
4. 商业授权材料仓库没有 → 相关判定 **N/A**；本报告不构成法律意见。

## 5. 关键数字速查

| 项 | 值 |
|---|---|
| 归档成员总数 | 407（147 + 196 + 64） |
| 已解析 / 未解析 | 397 / 10 |
| 解析层级分布 | build_log 240、exact_stem 82、symbol_lookup 52、stem_text 12、lt 别名 7、依赖 4、（未解析 10） |
| 声明类别 | gcc_runtime_exception 314、gpl 23、other_copyright 55、no_declaration 5 |
| 分发归档路径 | `.cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/lib/` |
| 源码根 | `.cache/xos_seed/gcc/source/gcc-16.2.0` |
| 未运行 | 完整构建、字节级逐成员溯源、反汇编、法律意见 |
