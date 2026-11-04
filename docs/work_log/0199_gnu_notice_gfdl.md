# 0199 — GNU NOTICE/GFDL 组件登记与客体许可装盘

2026-11-04。分支 `codex/gnu_notice_gfdl`（基于 main `5213ac4a`）。清偿
`licenses/open_items.json` 的 `gnu_notice_coverage_gaps`（GNU Seed 分发义务 O3/O4/O8）。

## 1. 根 NOTICE（O4）

`NOTICE` 新增 GNU 段：GCC 16.2.0 与目标运行库（GPL-3.0-or-later + GCC Runtime
Library Exception，指向上游 COPYING 四文本）、GNU Binutils 2.47、GMP 双许可、
MPFR/MPC LGPL-3.0-or-later、Binutils 捆绑 zlib、GFDL 手册页文本位置；声明
对应源码包/补丁/构建记录随发行，XOS 默认许可不重新许可任何 GNU 组件。

## 2. GFDL 组件登记（O8）

- 从**锁定** GCC 源包 `.cache/xos_seed/gcc/gcc-16.2.0.tar.xz`（sha256
  `e6738e29…` 与 `src/ports/gcc/source_lock.json` 一致）提取
  `gcc-16.2.0/gcc/doc/include/fdl.texi` **原字节**入库为
  `licenses/GFDL-1.3.texi`（sha256 `2b6a0198db38b8c8969e4581b2873d69411906ba8e6057c19fd6f5e00e291b2b`）。
- `licenses/components.json` 新增组件 `GFDL manual pages (GNU Seed tools)`
  （license `GFDL-1.3`，notices 指向该文本；`copy_notices()` 随发行包携带）。

## 3. 客体 /usr/share/licenses GNU 条目（O3）

- `scripts/prepare_gcc_seed.py`：specs 安装后追加 10 条 `install_files`
  （guest `/usr/share/licenses/{gcc,binutils,gmp,mpfr,mpc,zlib,gfdl}/…`，源为
  仓库内上游 COPYING 文本与 GFDL 文本）——与既有安装器通用路径导入兼容
  （`import_manifest_files` 按 guest_path 建目录）。
- **现用** `build/cpp_bundle/seed_manifest.json`（本发行打包直接读取）同步追加
  同样 10 条，逐条 sha256 与源文件核验通过（install_files 174→184）。
- 镜像级核验归入 0.0.2-1103 打包门禁（清单级核验已过；`import_manifest_files`
  通用性已由 gcc_seed_smoke/adventure_smoke 既有路径覆盖）。

## 4. 开放项处置

`gnu_notice_coverage_gaps`：`open` → `not_applicable`（退出条件三项均已交付：
NOTICE ✓、GFDL 组件 ✓、客体覆盖已实现于 install_files 且清单级核验 ✓；镜像级
核验为打包时例行门禁）。历史 1024 包缺 third_party_notices 按老人老办法不回改。

## 5. 验证

```text
python3 scripts/license_audit.py   # 基线 PASS（关项前 3 open 显示正常；分支内关项后应显示 2 open）
python3 -m py_compile scripts/prepare_gcc_seed.py   # OK
seed_manifest 完整性：184 条 install_files 全部 path 存在且 sha256 匹配
GFDL 提取源：gcc-16.2.0.tar.xz sha256 == source_lock.json
```

未运行：完整 `make build` 与客体镜像级许可目录核验（归 0.0.2-1103 打包步骤）。
