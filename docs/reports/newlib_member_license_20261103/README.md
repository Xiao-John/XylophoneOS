# newlib 归档逐成员 → 源码许可映射

2026-11-03 · 分支 `codex/ncursesw_w1` · D7 许可两叶之一（另两叶：
[GNU Seed 分发审查](../gnu_seed_distribution_20261103/)、
[Qt 静态分发审查](../qt_static_distribution_20261103/)）。
本目录只含本叶产物：`README.md`、`findings.json`、`manifest.json`（平铺根清单，按
[evidence_integrity](../../../contracts/evidence_integrity.md) 契约）。

**性质与边界**：这是**成员 → 源文件 → 文件头声明类别**的映射，不是逐成员法律意见，
也不是法律兼容性认证。权威的多来源条款仍在
`src/third_party/newlib/COPYING.NEWLIB`；其分节按各自标注的 target 适用（第 21/22 节
标为 `*-linux*` targets only，当前构建目标是 `x86_64-elf`）。
本叶未修改 `docs/licensing.md`、`scripts/license_audit.py`、`licenses/components.json`
及任何登记文件；登记更新由汇总者执行。

## 1. 方法

1. **成员枚举**：直接解析 GNU `!<arch>` 头（`scripts/newlib_member_license_map.py`
   `iter_archive_members`），正确处理 `//` 长名表与 `/十进制` 索引，剔除 `/` 符号表与
   `//` 名字表两个非成员条目。
2. **源文件解析（权威路径）**：取 newlib 构建树的 `*.o` 依赖文件
   `".deps/<成员名>.Po"`——它记录该对象**实际被编译的源文件路径**。用到三棵同源构建树：
   - `build/w1_final_acceptance/newlib/single/build/x86_64-elf`
   - `build/w1_final_acceptance/newlib/threaded/build/x86_64-elf`
   - `.cache/xos_seed/threading_newlib/build/x86_64-elf`

   **三树一致性实测**：三树共同记录的 **1028** 个成员中 **1028 一致、0 分歧**；
   合计覆盖 1029 个对象名。脚本按树优先级取首个记录。
3. **声明类别**：对解析出的源文件做**全文**声明扫描（不是只扫文件头，因为个别文件
   的版权写在 160 行之后），依次匹配 `spdx` / `lgpl` / `gpl` / `bsd_like` /
   `mit_like` / `other_copyright` / `no_declaration`，并记录命中的声明文本。
4. **回退规则**（本次未被触发）：无依赖文件时按源码树同名检索，优先通用目录、
   其次 `machine/x86_64|i386`，歧义如实上报为 `ambiguous`，不猜。

## 2. 结果

复核命令（路径模板）：

```sh
cd "${XOS_XOS_ROOT}"
python3 scripts/newlib_member_license_map.py --out docs/reports/newlib_member_license_20261103/findings.json
python3 tests/report_manifest_check.py    # 本目录应出现在 compliant 列表
```

| 指标 | 值 |
|---|---|
| 归档成员总数 | **1053**（`libc.a` **627** + `libm.a` **426**） |
| 唯一成员名 | 1028（`libc.a` 内含 25 个 `libm_a-` 前缀成员，与 `libm.a` 重名） |
| 唯一源文件 | 1028 |
| **成功解析** | **1053 / 1053（100%）**，全部经 `dependency_file` 路径 |
| 未映射 `unmapped` | **0** |
| 歧义 `ambiguous` | **0** |
| 解析回退到名字检索 | 0 |

**声明类别分布**（文件头/全文声明提取，非法务归类）：

| 类别 | 成员数 | 说明 |
|---|---|---|
| `bsd_like` | 359 | 含 "Redistribution and use in source and binary forms" 类声明 |
| `other_copyright` | 317 | 仅版权行，无许可正文 |
| `no_declaration` | 323 | 文件内无版权/许可声明；条款来源为 `COPYING.NEWLIB` 与登记材料 |
| `spdx` | 54 | `BSD-3-Clause` 30、`BSD-2-Clause-FreeBSD` 21、`BSD-2-Clause` 2、`MIT` 1 |
| `lgpl` / `gpl` | **0** | 见第 3 节独立复核 |

**独立复核（不依赖分类规则顺序）**：对 1028 个唯一源文件全文正则抓取
`Lesser General Public|Library General Public|GNU General Public License|\bLGPL\b|\bGPL\b`
→ **命中 0 个**。同一正则在整棵源码树（含本次目标未编译的端口）确实能抓到
11 个 LGPL 文件（集中在 `newlib/libc/sys/rdos/*`）与 1 个 GPL 文件，说明**抓取本身有效**，
只是这些文件不属于 `x86_64-elf` 目标构建。

## 3. 结论与边界

1. **可关闭的缺项**：`scripts/license_audit.py` 的
   `newlib_archive_member_to_source_license_mapping` —— 成员到源文件到声明类别的映射
   已全覆盖（1053/1053、0 未映射、0 歧义），可复算、可复核。
2. **不能由此声称的事**（C31：建设基础，而非制造已经完成的假象）：
   - 映射 ≠ 法律意见；`no_declaration` 的 323 个成员**不因此取得任何许可归属结论**，
     其条款仍以 `COPYING.NEWLIB` 与各分节自身条件为准。
   - "本目标构建的成员源文件头不含 LGPL/GPL 文本" ≠ "整个 newlib 不是 LGPL"。
     `COPYING.NEWLIB` 的多来源结构不变。
   - 未做逐成员字节溯源：**SDK 归档成员字节与本地三棵构建树的对象字节均不相同**
     （不同次构建），映射依据是成员名对源文件的稳定编码 + 三树 `.Po` 记录一致
     （1028/1028），而非同一批对象的字节链。
3. **已知限制**：
   - 构建树位于 `build/`（未入库），`.Po` 为本地构建产物；换机复算需重建 newlib 或
     用同样命名的依赖记录。
   - 未验证归档成员与 `.Po` 声明的对象是同一编译产物（同上，字节不匹配）。
   - 未做反汇编/符号级验证；未覆盖 `libgloss` 单独归档与未链接的 `libnosys`。

## 4. 关键数字速查

| 项 | 值 |
|---|---|
| `libc.a` 成员 | 627（`libc_a-` 602、`libm_a-` 25） |
| `libm.a` 成员 | 426（全 `libm_a-`） |
| 源码树根 | `build/w1_final_acceptance/newlib/newlib-4.6.0.20260123` |
| 依赖记录覆盖 | 1029 个对象名；三树共同 1028 个、一致 1028 |
| 声明类别 | bsd_like 359 / other_copyright 317 / no_declaration 323 / spdx 54 |
| LGPL/GPL 文本（唯一源文件） | 0 / 1028 |
| 未运行 | 完整构建、Release 打包、逐成员法律意见、字节级溯源 |
