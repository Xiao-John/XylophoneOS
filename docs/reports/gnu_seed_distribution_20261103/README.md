# GNU Seed 分发审查（future_GNU_Seed_distribution_review）

2026-11-03 · 分支 `codex/ncursesw_w1` · D7 许可叶之一（newlib 逐成员映射、Qt 静态分发审查由
其他叶交付，互不修改对方文件）。本目录只含本叶产物：`README.md`、`gnu_seed_inventory.json`、
`manifest.json`（平铺根清单，按证据完整性契约）。

**性质与边界**：本报告是**材料 + 发布流水线审查与义务清单**，不是逐成员法律意见，也不是
法律兼容性认证。`scripts/license_audit.py` 的 `passed` 只代表登记材料与 SDK 副本哈希一致。
本叶未修改 `docs/licensing.md`、`licenses/components.json`、`scripts/license_audit.py` 及任何
登记文件；发现的登记冲突只在第 3.4 节如实记录。

## 1. 盘点：仓库内 GNU 来源产物

| # | 组件 | 版本 | 来源锁（算法 · 值） | 许可声明材料位置 | 构建/打包入口 · 移植补丁 |
|---|---|---|---|---|---|
| 1 | GCC（C Seed + g++/cc1plus 主机闭包） | 16.2.0 | sha256 `e6738e29597f733270731aa90600f37ffdc045079dfc27ec7e8192cc81085c3e`（`src/ports/gcc/source_lock.json`） | `src/ports/gcc/upstream/`：GCC-COPYING、GCC-COPYING.RUNTIME、GCC-COPYING3、GCC-COPYING3.LIB（共 11 份文本，含 GMP/MPFR/MPC） | `scripts/build_gcc.py`、`prepare_gcc_seed.py`、`relink_gcc_seed.py`、`seed_preflight.py`；`src/ports/gcc/patches/` 8 个补丁 |
| 2 | GNU Binutils Seed（as/ld/ar/ranlib/strip/nm…） | 2.47 | sha256 `154ab23b60070e8f27013c22977f1129425d67d1e8acd6e13010e617811e4cff`（`src/ports/binutils/source_lock.json`） | `src/ports/binutils/upstream/`：COPYING、COPYING.LIB、COPYING3、COPYING3.LIB、zlib-LICENSE（5 份） | `scripts/build_binutils.py`；`src/ports/binutils/patches/` 6 个补丁 + `series` |
| 3 | 捆绑 zlib（Binutils 内部静态库） | 1.3.1 | 并入 binutils 原包（`source_lock.json` 的 `bundled_components`） | `src/ports/binutils/upstream/zlib-LICENSE` | 同上，不依赖宿主 zlib |
| 4 | GMP（GCC 构建依赖，进源码树） | 6.3.0 | sha512 `3b684c9bcb9ede2b7e54d0ba4c9764bfa17c20d4f3000017c553b6f1e135b536949580ff37341680c25dc236cfe0ba1db8cfdfe619ce013656189ef0871b89f8` | `src/ports/gcc/upstream/`：GMP-COPYING、GMP-COPYINGv2、GMP-COPYINGv3、GMP-COPYING.LESSERv3 | `scripts/build_gcc.py` 的 `dependency_tree()`（解到 GCC 源码树内） |
| 5 | MPFR | 4.2.2 | sha512 `0176e50808dcc07afbf5bc3e38bf9b7b21918e5f194aa0bfd860d99b00c470630aef149776c4be814a61c44269c3a5b9a4b0b1c0fcd4c9feb1459d8466452da8` | `src/ports/gcc/upstream/MPFR-COPYING`、`MPFR-COPYING.LESSER` | 同上 |
| 6 | MPC | 1.3.1 | sha512 `4bab4ef6076f8c5dfdc99d810b51108ced61ea2942ba0c1c932d624360a5473df20d32b300fc76f2ba4aa2a97e1f275c9fd494a1ba9f07c4cb2ad7ceaeb1ae97` | `src/ports/gcc/upstream/MPC-COPYING.LESSER` | 同上 |
| 7 | newlib（SDK libc.a/libm.a/头文件） | 4.6.0.20260123 | 仓库内**无上游摘要锁**；`licenses/components.json` 记源包 sha256 `6ff27e3bf022666f43f7802255be680eeff722ac181b1725d21e2e8318604ee3`（实测标识，非上游认证；1024 源码包同值） | `src/third_party/newlib/COPYING.NEWLIB`（逐文件多许可，含仅 Linux target 的第 21/22 节）+ 头文件内声明 | `scripts/build_newlib.sh`、`build_utf8_newlib.py`、`build_threading_newlib.py`；`src/ports/newlib/patches/0001-reject-utf8-surrogates.patch` |
| 8 | GCC 目标运行库 libgcc.a / libstdc++.a / libsupc++.a | 16.2.0 目标件 | 实际分发件绑定 `.cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/manifest.json`（忽略缓存，随发布 SDK 复制为 `target_runtime_provenance.json`）：libgcc `1d1755fe…c994dfa`、libstdc++ `18da9426…11256d`、libsupc++ `2e3ae7ef…5bfe76` | `src/ports/gcc/upstream/GCC-COPYING.RUNTIME`（GCC 运行库例外） | `scripts/relink_gcc_seed.py`、`config/release_cpp_runtime_v5.json`（`manifest_sha256 fe685d9f…`） |

**静态归档成员数**（按 AR 头解析实测，剔除 \`/\` 符号表与 \`//\` 名字表两个非成员条目；
`ar t` 行数 = 下列成员数 + 2）：分发件 libgcc.a **147**、libstdc++.a **196**、
libsupc++.a **64**（GCC 侧合计 **407**，取 `target_runtime_v5_receipt` 副本）；newlib
libc.a **627**（含 25 个 `libm_a-` 前缀成员）、libm.a **426**（合计 **1053**，属 newlib
成员映射叶的范围，本叶只登记数字）。
> 复核说明：本报告初稿此处写作 144/125/49 与 199/196，为**错误值**，已由汇总者按
> AR 头解析订正（同一命令下 `.cache/xos_seed/gcc/e08_5` 与 `target_runtime_v5` 各副本
> 成员数一致或差 1，均为 147/196–197/64–65 量级）。

**许可类别（GNU 相关，本叶归类计数 = 8）**：
① GPL-3.0-or-later（gcc/g++/cc1/collect2、as/ld 等可执行工具）；
② GPL-3.0-or-later **带 GCC Runtime Library Exception**（libgcc/libstdc++/libsupc++/crtbegin/crtend）；
③ LGPL-3.0-or-later（MPFR、MPC）；
④ GMP 双许可（LGPLv3/GPLv3，`GMP-COPYING.LESSERv3`+`GMP-COPYINGv3`+`GMP-COPYINGv2`）；
⑤ Zlib（binutils 捆绑 zlib 1.3.1）；
⑥ newlib 逐文件多许可（`COPYING.NEWLIB`，含 BSD 类与 LGPL；第 21/22 节标注仅 `*-linux*` target）；
⑦ GFDL（随工具分发的手册页，如 work disk 上的 `man7/GFDL.7`、`GPL.7`）；
⑧ Apache-2.0（XOS 自研移植补丁与构建脚本，上游上下文保留原条款）。
> 归类来自登记材料与声明文本的**清点**，不是逐文件法律判定。

## 2. 分发状态判定

### 2.1 已发布发行（本地字节与公开摘要全部比对通过）

| 发行 | 发布时间 | 资产数 | 与 GNU Seed 相关的资产 | 本地核对 |
|---|---|---|---|---|
| 0.0.1-1024（tag `v0.0.1-1024`） | 2026-10-24 | 8 | `xos-0.0.1-1024-gnu-sources.tar.gz`（176,472,043 B）、`…-gnu-source-supplement-gxx-lrealpath.tar.gz`（179,934 B）、images/sdk/source | images、sdk、两个 GNU 源码包的本地 sha256 与 `public_CHECKSUMS.sha256` **全部 MATCH** |
| 0.0.1-1026（tag `v0.0.1-1026`） | 2026-10-26 | 5 | `xos-0.0.1-1026-sources.tar.gz`（206,421,996 B，内含 1024 两份 GNU 对应源码包原样副本）、images、sdk | 三者本地 sha256 与 `docs/releases/release_0_0_1_1026.json` 回执 digest **全部 MATCH**（images `8dcc344f…`、sdk `a09e6157…`、sources `3f1ead98…`） |

**对 0.0.1-1026 images 包内 `work_disk.img` 做只读 FAT32 目录解析**（不落盘、不改镜像），实测存在：

- `/usr/bin/`：`x86_64-elf-gcc`、`x86_64-elf-gcc-16.2.0`、`x86_64-elf-g++`、`x86_64-elf-cpp`、
  `x86_64-elf-gcc-{ar,nm,ranlib}`、`x86_64-elf-gcov{,-dump}`、`x86_64-elf-as`（另有无前缀 `as`）、
  `x86_64-elf-ld`、`x86_64-elf-{ar,ranlib,strip,nm}` —— GCC 与 Binutils Seed 可执行件；
- `/usr/libexec/gcc/x86_64-elf/16.2.0/`：`cc1`（47,587,544 B）、`cc1plus`（50,529,152 B）、`collect2`；
- `/sysroot/lib/`：`libgcc.a`、`libstdc++.a`、`libsupc++.a`、`libc.a`、`libm.a`；
- `/usr/share/man/man7/`：`GPL.7`、`GFDL.7`、`fsf-funding.7`；
- `/usr/share/licenses/`：只有 `cpython`、`zlib`、`python_idna`，**无 GNU 条目**（缺口见第 4 节）。

`release_manifest.json` 的客体文件里 `x86_64-elf*` 相关条目 1024 与 1026 **同为 170 项**
（1024 总计 1210 项，1026 总计 1778 项），说明两次发行的工作盘都携带了 Seed 工具与运行库。

### 2.2 逐项判定表

| 产物 | 0.0.1-1024 | 0.0.1-1026 | 0.0.2-1103（本轮定版、**未打包**） |
|---|---|---|---|
| GCC Seed 工具（gcc/g++/cpp/cc1/cc1plus/collect2/gcov…，seed manifest `install_files` 174 项） | **随发行**（工作盘） | **随发行**（工作盘） | **将随发行**：`scripts/package_release.py` 把 `seed['install_files']+sysroot['files']` 写入工作盘；打包未执行，实际以冻结产物为准 |
| Binutils Seed（as/ld/ar/ranlib/strip/nm） | **随发行** | **随发行** | **将随发行**（同上；`required_tools` 预检含 `as/ld/ar/ranlib`） |
| GCC 运行库 libgcc/libstdc++/libsupc++ 于工作盘 `/sysroot/lib` | **随发行** | **随发行** | **将随发行**（同上） |
| GCC 运行库于 **SDK `cpp/lib/`** | **否**（1024 SDK 无 `cpp/`） | **是**（三件套 + `target_runtime_provenance.json`） | **将随发行**（`package_release.py` 第 190–194 行固定复制） |
| newlib libc.a/libm.a/头文件（SDK 与工作盘） | **随发行** | **随发行** | **将随发行** |
| GMP/MPFR/MPC（进 GCC 源码树、静态并入工具二进制） | **随二进制间接携带** | **随二进制间接携带** | **将随二进制间接携带**（同第 1、2 行） |
| GNU 对应源码包（原包 + 补丁 + 覆盖层 + 构建记录） | **随发行**（独立 176 MB 资产 + 补遗） | **随发行**（源码包内 `unchanged_gnu_correspondence/` 原样携带 1024 两包） | **未执行**：`package_release_materials.py` 有门禁——`build/cpp_bundle/seed_manifest.json` 的 sha256 必须等于 1024 记录值，当前实测 `327e2cb0f548dfb721b9ca968c2d3ec84f01e7633b0b3e9d5207bf3c7b5ea448` 与 1024/1026 **完全一致（Seed 未变）**，因此脚本会复用 1024 对应材料；若打包前 Seed 变更，脚本直接失败并要求重新生成对应材料 |
| 许可声明文本（COPYING/例外） | **部分**：images/SDK 根只有 `LICENSE`、`NOTICE`、`COPYING.NEWLIB`、`licenses/`（**无 third_party_notices**）；GNU 文本在源码包 `materials/` 内 | **是**：images 与 SDK 均带 `third_party_notices/` **27 份**（其中 GCC/GMP/MPFR/MPC/binutils/newlib 相关 17 份） | **将随发行**（`copy_notices()` 按 `components.json` 的 `notices` 复制全部登记文本） |
| `.cache/xos_seed/` 原始缓存 | **不发布**（`.gitignore` 第 21 行忽略；打包器只挑选原包、源码树差异、manifest 与日志） | 同左 | 同左 |

**0.0.2 的最终答案在打包冻结时才成立**：`build/releases/0.0.2-1103/` 目前不存在，`VERSION`
已定为 `0.0.2-1103`（工作区改动，非本叶所写），`docs/releases/next_release.md` 明确“冻结/打包/
上传未执行”，其“下一次发行时的工作”第 4 条就是“生成对应新源码材料及许可声明”。

### 2.3 发布流水线（`scripts/`）核对结论

- `package_release.py`：冻结 images + SDK；工作盘装入 seed 安装清单；SDK 追加 GCC 运行库三件套；
  `copy_notices()` 向 images 与 SDK 写入 `LICENSE/NOTICE/COPYING.NEWLIB/licenses/third_party_notices`；
  `release.json` 记录 `seed_manifest_sha256` 与逐客体文件哈希。
- `package_release_sources.py`：输出目录**硬编码**为 `build/releases/0.0.1-1024/sources`，只服务 1024；
  按 `source_lock` 校验 GCC/GMP/MPFR/MPC/Binutils 原包摘要，newlib 无锁、记实测值；生成
  `source-materials-manifest.json`（含 overlays 与 deleted 清单），并在 README 中声明
  “不认证逐成员许可或库对象来源”。
- `package_release_materials.py`：按 `VERSION` 写 `build/releases/<版本>/sources/`；Seed 变更即中止；
  附 `git archive` 的跟踪源快照与构建记录。
- `release_smoke.py` / `sdk_receipt.py`：验 SDK/运行库绑定与行为，不做许可法律判定；
  许可材料一致性由 `make license-audit`（`scripts/license_audit.py`）覆盖。

### 2.4 登记冲突（如实记录，本叶不修改）

1. `docs/licensing.md`“GNU Seed 的当前边界”称 Seed“仅构建到忽略的缓存……**没有公开发布**”，
   与 2.1 的已发布资产事实**矛盾**（1024/1026 工作盘与 SDK 实际携带 Seed 工具与运行库）。
2. `licenses/components.json` 中 GCC Seed、Binutils Seed、GMP、MPFR、MPC 的
   `distribution_status` 为 `local_only; …not_completed`，同上与事实不符。
3. `src/ports/gcc/e08_5_target_runtime_manifest.json`（仓库内）记录 libstdc++ 为 `8bba188c…`，
   而实际分发件是 `18da9426…`（绑定 target_runtime_v5 receipt）。两份运行库 manifest 并存，
   引用时不可混用。
4. 上述文件不在本叶写入范围，**未作修改**；应由有权修改者按本报告更新，避免“登记说不分发、
   资产里已分发”的持续性错误陈述。

## 3. 未来若分发所需的义务清单（与现有材料对照）

依据 `docs/licensing.md` 第 6 节与“GNU Seed 的当前边界”，逐项对照：

| # | 义务（未来分发时必须满足） | 现有材料 | 缺口 / 状态 |
|---|---|---|---|
| O1 | **对应源码**：每个随发行二进制的首选修改形式——上游原包（摘要锁）+ 全部 XOS 补丁 + 构建脚本与 configure 选项 + 实际源码树差异覆盖层 | 1024 `gnu-sources.tar.gz`（GCC/Binutils/GMP/MPFR/MPC/newlib 原包 6 个、overlays 3 份：gcc-c 3300、gcc-cpp 3300、binutils 325 路径，GMP 2343 / MPFR 591 / MPC 357 路径全量入包）+ 补遗（lrealpath 派生件）；仓库内 8+6 个补丁与 `scripts/` 构建脚本 | 已履行（1024/1026）；**Seed 变更后须重新生成**（脚本门禁已具备） |
| O2 | **同批交付**：源码与二进制在同一发行、同一介质提供并入校验表 | 1024 两个源码资产 + `public_CHECKSUMS.sha256`；1026 源码资产 + 回执 digest | 已履行；0.0.2 打包时按 `next_release.md` 第 4 条重做 |
| O3 | **GCC 运行库例外**：libgcc/libstdc++/libsupc++/crt 伴随例外文本 | `GCC-COPYING.RUNTIME` 在仓库；1026 images/SDK `third_party_notices` 携带 | **1024 images/SDK 无 `third_party_notices`**；**盘上 `/usr/share/licenses` 无 GNU 条目** |
| O4 | **NOTICE/版权归属**：发行材料列出 GNU 组件与其声明 | 根 `NOTICE` 仅写 FatFs 与 newlib；SDK 根带 `COPYING.NEWLIB`；1026 带 27 份 third_party_notices | **根 `NOTICE` 缺 GNU Seed/Binutils/GMP/MPFR/MPC 条目**；发行文案未显式声明 |
| O5 | **静态归档逐成员追溯**：库成员 → 源码许可证映射 | 无 | **NOT_RUN**：GCC 运行库 407 成员、newlib 1053 成员（另叶）；`components.json` 已保留该缺项 |
| O6 | **编译器许可与生成程序许可分离**：不得把工具的 GPL 自动套到用户程序 | `docs/licensing.md` 第 6 节已有原则 | 发行 README/文案未显式写出，建议补一句 |
| O7 | **LGPL/GPL 组件条款**：GMP 双许可、MPFR/MPC LGPL、binutils 捆绑 zlib 的声明随件保留 | 文本齐备且 1026 已随 SDK/images 携带 | 1024 包内缺失（仅在源码包） |
| O8 | **GFDL 文档**：随工具分发的手册页（`GFDL.7`/`GPL.7`/gcc.1 等） | 实际随工作盘分发（2.1 实测） | 未在 `components.json` 登记为独立条目 |
| O9 | **构建记录与 provenance**：manifest 绑定输入/输出哈希 | `seed_manifest.json`、`sysroot_manifest.json`、target_runtime_v5 receipt、binutils build manifest 均随源码包/SDK | 记录内含历史宿主绝对路径，对外引用须按证据契约做路径模板化处理（本报告已用 `${XOS_XOS_ROOT}`/`${XOS_TOOLCHAIN}`/`${XOS_TMPDIR}`） |
| O10 | **法律审查与成员级结论** | — | **NOT_RUN**：本报告不提供法律意见；材料检查通过 ≠ 法律审查完成 |

## 4. 结论

**审查层面：可结项。** 理由（四项均可核验）：

1. **盘点完成**：6 个 GNU 来源源码组件（GCC、Binutils、GMP、MPFR、MPC、newlib）+ 3 个 GCC
   运行库归档 + 2 个 newlib 归档，版本、来源锁哈希、许可声明材料位置、构建/打包脚本与补丁数
   全部落表（第 1 节与 `gnu_seed_inventory.json`）。
2. **分发状态逐项判定完成**（第 2 节）：1024/1026 的“已随发行”有本地字节与公开摘要 MATCH、
   工作盘目录实测双重证据；0.0.2-1103 的“将随发行 / 未执行”由流水线代码与门禁逐条推出。
3. **义务清单明确**（第 3 节 O1–O10），并与现有材料逐条对照，缺口全部点名。
4. **对任务前提的更正（诚实结论）**：本叶**不能**写成“当前不分发 = 义务不触发”。事实是
   0.0.1-1024 与 0.0.1-1026 **已经公开分发** GNU Seed 工具与 GCC 运行库，义务**已被触发且
   已大部分履行**（对应源码包、补丁、构建记录随发行发布，1026 起声明文本随包携带）；尚未
   履行的是 O3/O4/O5/O7/O8 中列出的缺口。0.0.2-1103 打包时义务**再次触发**，按第 3 节清单
   复核即可，不需要重开本审查。

**残余风险（不阻塞本叶结项，须继续跟踪）：**

- **R1** 登记冲突未清：`docs/licensing.md`“没有公开发布”与 `components.json`
  `local_only` 与已发布资产矛盾（2.4）。修改权不在本叶。
- **R2** 逐成员追溯 NOT_RUN：GCC 运行库 407 成员未映射；newlib 1053 成员由另叶处理。
- **R3** 声明覆盖不均：1024 images/SDK 无 `third_party_notices`；盘上 `/usr/share/licenses`
  无 GNU 条目；根 `NOTICE` 缺 GNU 条目。
- **R4** 0.0.2-1103 未打包，本报告的“将随发行”是流水线判定，不是已冻结事实；若打包前 Seed
  变更，必须先重新生成对应源码材料（现有脚本会拒绝复用）。
- **R5** 双运行库 manifest 并存（2.4 第 3 条），引用错源会导致 provenance 断链。
- **R6** GMP/MPFR/MPC 静态并入是**构建方式推断**（GCC 默认 in-tree 静态便利库 + 覆盖层含其
  全量源码），**未对二进制做成员级反汇编验证（NOT_RUN）**。
- **R7** 本报告是材料与流水线审查，**不构成法律意见**；不得据此声称“GNU 分发已通过法律审查”。

**关于关闭 `license_audit.py` 的 `future_GNU_Seed_distribution_review`：** 本叶交付的是审查报告
与义务清单；`scripts/license_audit.py`、`licenses/components.json`、`docs/licensing.md` 不在本叶
写入范围，本叶**未修改**。本叶只证明“审查”这一层已完成，不冒充登记已更新。
> 后续（同一 PR 内，2026-11-03）：汇总者已执行该授权编辑——`not_completed` 现为空并改为
> 以 `review_reports` 引用三份审查报告；`licenses/components.json` 的 5 条 `local_only`
> 分发状态与 `docs/licensing.md` 的“没有公开发布”表述也已按本报告第 2.1 节事实更正。

## 5. 关键数字

| 指标 | 值 |
|---|---|
| GNU 来源源码组件（盘点） | 6（GCC、Binutils、GMP、MPFR、MPC、newlib） |
| GCC 运行库归档 | 3（libgcc.a、libstdc++.a、libsupc++.a） |
| 许可类别（GNU 相关归类） | 8 |
| 来源锁条目 | 5 有锁（GCC sha256、Binutils sha256、GMP/MPFR/MPC sha512）+ newlib 无上游锁（仅实测 sha256） |
| 移植补丁 | GCC 8 + Binutils 6 + newlib 1 = 15 |
| 许可声明文本（仓库） | `src/ports/gcc/upstream` 11 + `src/ports/binutils/upstream` 5 + `COPYING.NEWLIB` 1 = 17 |
| 未映射静态归档成员 | GCC 运行库 **407**（147+196+64）；newlib **1053**（627+426，另叶） |
| 已发布发行 | 2（0.0.1-1024 资产 8、0.0.1-1026 资产 5），本地字节与公开摘要 **7/7 MATCH** |
| 工作盘 Seed 相关客体文件 | 170（1024 与 1026 同） |
| 1026 `third_party_notices` | 27 份（GNU 相关 17） |
| 1024 GNU 源码包 | 176,472,043 B + 补遗 179,934 B |
| Seed manifest（未变） | sha256 `327e2cb0f548dfb721b9ca968c2d3ec84f01e7633b0b3e9d5207bf3c7b5ea448`（=1024=1026） |
| 0.0.2 打包状态 | `build/releases/0.0.2-1103/` 不存在 → 未打包 |

## 6. 未运行 / 未执行（按纪律如实标注）

- **未运行**完整构建 `python3 scripts/build.py`（耗时且单构建者规则；本叶只读使用现有
  `build/` 与 `build/releases/` 产物）。
- **未执行** 0.0.2-1103 的冻结、打包、上传（`package_release*.py`、`release_smoke.py` 均未运行）。
- **未运行** `scripts/license_audit.py`（会改写 `build/license_report.json`，非本叶文件）。
- **未做** 二进制成员级反汇编验证（R6）、逐成员许可映射（R5/O5）、法律意见（O10）。
- **未修改**任何登记文件、脚本、`build/` 产物；未 commit/push/建分支。

## 7. 复核命令（路径模板，避免宿主绝对路径）

```sh
cd "${XOS_XOS_ROOT}"
python3 tests/report_manifest_check.py                     # 本目录应出现在 compliant 列表
python3 tests/check_public_evidence_paths.py --index --base origin/main
python3 - <<'PY'                                          # 已发布资产本地字节核对
import hashlib, json, pathlib
sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
checks = dict(line.split()[::-1] for line in pathlib.Path(
    'build/releases/0.0.1-1024/public_CHECKSUMS.sha256').read_text().splitlines() if line.strip())
for name in ('xos-0.0.1-1024-gnu-sources.tar.gz',
             'xos-0.0.1-1024-gnu-source-supplement-gxx-lrealpath.tar.gz'):
    p = pathlib.Path('build/releases/0.0.1-1024/sources') / name
    print(name, sha(p) == checks[name])
PY
```

工作盘内容核对为**只读** FAT32 目录遍历（不导出、不改写镜像）；命令与结论见第 2.1 节。
