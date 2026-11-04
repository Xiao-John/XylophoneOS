# 0200 — GCC 运行库 10 未映射成员人工裁定

2026-11-04。分支 `codex/gcc_member_manual_rulings`（基于 main `51fcec92`）。
清偿 `licenses/open_items.json` 的 `gcc_runtime_member_mapping_unresolved`
（退出条件第一路径：10 个成员全部解析或逐个人工裁定并记录）。

## 1. 方法

对自动化 pass（2026-11-03，`findings.json` 的 `unmapped[]` 10 项）逐个取证：

- `x86_64-elf-nm` / Python `!<arch>` reader 提取成员符号；
- 构建日志 `ln -s <full path> <local name>` 与 `libtool -c <src> -o <obj>` 行；
- `libgcc/Makefile.in` 对象规则（`lib2funcs-o: %$(objext): $(srcdir)/libgcc2.c` 等）；
- 源码定义位点（`libgcc2.c` 的 `L_clz`/`__mulbitint3`/`NAME__MAIN` 等）。

## 2. 裁定结果（10/10，证据见 `manual_rulings.json`）

| 成员 | 归档 | 裁定源 | 关键证据 |
|---|---|---|---|
| `__main.o` | libgcc | `libgcc/libgcc2.c` | Makefile:513 lib2funcs 规则；`NAME__MAIN` |
| `_ctors.o` | libgcc | `libgcc/libgcc2.c` | 同上；与 `__main.o` 字节相同（sha `59b0937c`） |
| `_clz.o` | libgcc | `libgcc/libgcc2.c` | `L_clz` 定义 `__clz_tab`（:669）；nm `R __clz_tab` |
| `_divmodbitint4.o` | libgcc | `libgcc/libgcc2.c` | Makefile:482 列表 + :513 规则 |
| `_mulbitint3.o` | libgcc | `libgcc/libgcc2.c` | Makefile:461；定义 :1468 |
| `enable-execute-stack.o` | libgcc | `libgcc/enable-execute-stack-empty.c` | 构建日志 `ln -s`（XOS 空桩） |
| `floatunsitf.o` | libgcc | `libgcc/floatunsitf.c` | 两候选均定义 `__floatunsitf`；x86_64 硬件 FP 走经典文件；**字节级 pin 留待下次重建 member_manifest** |
| `basic_file.o` | libstdc++ | `libstdc++-v3/config/io/basic_file_stdio.cc` | 构建日志 `BASIC_FILE_CC=…` |
| `collate_members_cow.o` | libstdc++ | `…/config/locale/generic/collate_members.cc` | 构建日志 `ln -s generic/…` |
| `messages_members_cow.o` | libstdc++ | `…/config/locale/generic/messages_members.cc` | 构建日志 `ln -s generic/…` |

**declaration_category 全部裁定 `gcc_runtime_exception`**（GPL-3.0-or-later WITH
GCC Runtime Library Exception）——libgcc/libstdc++ 运行库统一条款，与已映射 314 个
同类成员一致。裁定为证据型工程结论，**非法务意见**；`floatunsitf.o` 的字节级源
钉按契约留给下次 GCC 重建的 `member_manifest.json`（退出条件第二路径的兜底）。

## 3. 产出与登记

- `docs/reports/gcc_runtime_member_license_20261103/manual_rulings.json`（新）+ README 追加节；
  目录平铺 `manifest.json` 重生成（3 文件）。
- `findings.json` **保持原样**（自动化 pass 历史记录，不回写）。
- `open_items.json`：`gcc_runtime_member_mapping_unresolved` → `not_applicable`（附裁定理由）。

## 4. 验证

```text
python3 tests/report_manifest_check.py   # 该目录 manifest 覆盖 3 文件
python3 tests/check_public_evidence_paths.py --commit HEAD --base origin/main
# 构建日志/Makefile 引用均为仓库内路径或 .cache 源树路径（不入 diff 新增行）
```

未运行：完整 GCC 重建与 `member_manifest.json` 契约产物（退出条件第二路径，下次重建时执行）。
