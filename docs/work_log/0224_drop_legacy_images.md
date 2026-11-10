# 0224 废除 legacy 引导支持：xos.img / xos.iso / legacy_images_available 移除

用户指令（2026-11-09）：“放弃 legacy 支持”。背景：内核在 `c82bd8aa` 已达 659552 字节
（`fdadfe77` 时 512080，#91/#93/#95 VM 与 #96 音频改动越过 512 KiB 门槛），
`scripts/build.py` 按设计不再产出 `xos.img`，**20+ 个引用 `artifacts['xos.img']` 的
客体 smoke 在基线即 `KeyError`**（`0216_s3_contest_report_fixes` 已记录，基线 stash 对照实证）。
本组在分支 `codex/drop_legacy_images`（基于 origin/main `c82bd8aa`）上彻底移除
legacy 概念并把全部消费方迁移到唯一常规引导产物 `build/xos-install.iso`。

**不废除**：`real_mode.img`（16 位练习，仍可软盘引导）、全部 FAT 工作盘
（`make work_disk`，superfloppy 一词指工作盘，与 legacy 无关）、`xos-install-dash.iso`
安装 ISO、`kernel_loader_iso*.bin`（ISO 用 loader）、`kernel_loader.asm` 源文件
（保留源码与 `px4a_source_audit` 引用，仅移除其构建与产物）。

## 设计决策

1. **唯一常规引导 = file-backed `xos-install.iso`**（boot sector + kernel_loader_iso_file
   经 ATAPI 读 KERNEL.BIN，无 640 KiB 实模式窗口限制）。嵌入式 `xos.iso` 与裸盘
   `xos.img` 同属 legacy（前者同样受实模式窗口约束），一并移除。
2. **引导介质按后缀自动判别**：`tests/boot_smoke.py` 的 `Guest(..., iso=None)`——
   `.iso` 走 `-cdrom`，其余（real_mode.img）保留软盘分支。一处覆盖全仓 55 个
   “变参镜像”引导点（qt6/aurora/ssg/browser 家族），无需逐个加 `iso=True`。
3. `scripts/run_qemu.py`：默认镜像 = `xos-install.iso`；删除 `--iso` flag；
   `--image` 按后缀判介质；软盘分支仅剩 real_mode 用途。
4. Makefile：删 `run_iso`（引用已废除 flag）；`run_vga` 改 `--iso-file`；
   `run_floppy` 目标名保留（用户习惯）注释标明现引导 ISO。
5. `tests/iso_capacity_compat.py` **删除**：其存在意义即 legacy 兼容矩阵
   （断言 `legacy_images_available` 且引导 floppy/embedded/file 三镜像），全仓无调用方。
   `iso_capacity_smoke` 的 `not legacy_images_available` 断言改为
   `.img/.iso` 产物集合恰为 `{xos-install.iso, real_mode.img}`。
6. 打包/发布链：`package_release.py` 校验与复制改 `xos-install.iso`
   （`xos_sha256` 字段名保留、值改指 install ISO——grep 证实该字段无下游消费方）；
   `release_pipeline.sh` cp 行同步；`modern_apps_freeze`/`prepare_daily_sdk`/
   `threading_qualification` 的镜像哈希迁移；`release_sdk_binding.py` 校验当前打包
   输出（非冻结发行），fixture 与断言同步，11/11 通过。冻结发行记录
   （`docs/releases/0.0.*`、`docs/reports/**`、历史 work_log）一律未改。
7. **kernel_smoke 叶表布局修正（迁移暴露的真问题）**：活页表断言原先从
   dump 偏移 0x3000（物理 0x4000）读叶表——那是**软盘 loader** 的布局；ISO loader
   （`kernel_loader_iso_file.asm`）的叶表在 `page_table_base=0x10000`（PML4/PDPT/PD 仍在
   0x1000–0x3000，PDE 走查本就正确）。该测试的 ISO 路径在基线从未跑过（先被
   `KeyError` 挡住）。修复：追加 pmemsave 0x10000/0x2000 读前两张叶表（覆盖 VA 0–4 MiB，
   内核映像所在），其余硬编码地址核查过全仓仅此一处（其余 pmemsave 均为动态地址）。
8. **SPDX 欠账一次补齐（19 文件）**：`make smoke` 恢复后 license_audit 首次真正跑到
   #90（Interactium/Aurora）合入的源码，暴露 `src/ports/qt6/aurora/**` 17 个自研文件 +
   `tests/interactium_aurora_guest.py` + `tests/fixtures/qt6/resources_rc.py` 缺
   Apache-2.0 标识（基线既有欠账——当时 smoke 已因 legacy 断裂无人跑到审计步）。
   按 Discipline“新自研代码 Apache-2.0”补 `#`/`// SPDX-License-Identifier: Apache-2.0`。
   `src/ports/make/upstream/**`（GNU make 上游源）经 `vendored_source_files` 登记，不碰、
   不加错误标识（复刻扫描初版漏了 vendored 跳过集，属假阳性）。

## 变更规模

115 文件（114 修改 + 1 删除）+ 19 个 SPDX 补头（计入修改数）：tests ~87、scripts 8、
docs 9、src/ports 17、Makefile、README。`src/kernel`、`src/user`（除 SPDX 注释行）零改动。

## 证据（2026-11-10，build `d00e4d10725565e8`，kernel 659552 字节）

```text
python3 scripts/build.py        产物：xos-install.iso + real_mode.img（无 xos.img/xos.iso）；
                                manifest 无 legacy_images_available；.img/.iso 产物恰两项
make smoke                      全绿（基线断裂的套件首次完整跑通）：
  boot 6 | kernel 18 E02 | task 12 E03 | process 13 E04 | file 8 E05 |
  persist 4 E07 | full_disk 1 E07-full | libc 3 E06 | e08_storage 9 E08-1 |
  runtime 5 E08-2 | license_audit PASS（9 license materials, open 0）
抽查（smoke 之外的迁移家族）：
  tests/iso_boot_smoke.py             passed
  tests/interactium_guest.py          passed（截图 build/interactium_demo.png）
  tests/file_posix_guest.py           PASS 11 checks（中央 e08 boot 助手迁移的深客体验证）
  tests/package_p2_persistent_gate.py passed 7 checks
  tests/release_sdk_binding.py        11/11（打包链迁移）
静态：
  全部改动 .py py_compile 通过；
  grep 'xos\.img|xos\.iso|legacy_images_available'（scripts/tests/Makefile/README/docs，
  排除冻结 work_log/history/reports/releases 与 __pycache__）= 0 命中
```

工具：Python 3.12.15、QEMU 11.1.2、x86_64-elf-g++ 16.2.0、Apple clang 21.0.0。

**证据路径检查（3 处已说明的误报）**：`check_public_evidence_paths.py --index
--base origin/main` 报 `NOT_PUBLIC_READY`，3 处 `private_temp/HOST_SPECIFIC_COMMAND`
命中全部是**客体文件系统内的 `/tmp` 路径**——`cpython_py0b_smoke` 的客体脚本
（`python3 /tmp/hello.py` 等 6 处）、`daily_utilities_p2_guest` 的客体 `/tmp/du`、
`dash_c3_exec_smoke` 的客体 `/tmp/work`；均已核对 `git show origin/main` 同样存在
（本组未新增任何一处），非宿主特定路径。`private_temp` 正则不区分客体/宿主 `/tmp`，
检查器亦无豁免参数。未游戏检查器、未改门禁工具；根治需让检查器识别客体路径上下文
（属门禁工具改动，留待裁决，不擅自放宽）。

## 失败 / 未运行 / 本组发现的既有问题

- **`tests/dash_c1_smoke.py`（续，2026-11-10 调查更新）**：
  1. **契约之罪已修**（第一被告，见 issue #99）：根因 = #66（`48882c92`，11-03）
     把 `sys_pipe_wait` 的 `third` 从“必须为 0 否则 -2”改为显式截止时间(ns)，探针
     仍按 10-26 旧契约断言。已将 `pipe_probe.c:84` 改写为新契约三断言（reader 索要
     size→-2；就绪 writer 携带截止→0；空 reader 过期截止→-13——后者补上 #66 登记
     欠缺的截止时间客体验收）。重跑：**`raw` 及其后 11 条命令全过**，死于第 13 条。
  2. **spawn 洪流已归案**（第二被告，卷宗 issue #104）：内核 `event=started` 加桩
     实测 = `name=audio_servi`（audio_service），parent=7，约每秒 1 只、全程 ~93 只。
     根因链：audio_service 非 supervisor（`supervisor=true` 仅自举创建）→ 启动时
     `sys_image_info` 遭内核 supervisor 门禁拒绝（id=1 即 denied）→ `tone_image=0`
     → `xos_user_main` 恒 `return 10`（毫秒级退出，outcome=1 code=10 实测 84 次）→
     `ensure_audio_service` 按 1s 退避永续重生。audio_tone 在镜像目录第 15 项、
     `image_info.name[16]` 无截断——纯权限门禁问题；AU 线“客体验收待工具链”
     故从未显形。**该洪流不打 `[wait]` 行、不污染测试断言，非超时元凶**。
  3. **closed_stdin 断点未结**（第三被告，现为 C1 唯一阻塞）：手法已逐环复原——
     `exec 0<&-` 后 fd0 空闲 → 阶段 A `pipe()` 把读端分配到 fd0 → 收尾恢复循环按
     “原 stdin 关闭”执行 `close(0)` 误杀读端 → `previous=0`（已死）→ 阶段 B
     `dup2(0,0)` 因 `valid_fd(0)=false` 报 EBADF → `pipeline: stdin` → dash 退 2。
     但同手法在 10-26 通过了 25 项中的本项（`dash_c1_20261026` 在案），回归向量
     未锁定；嫌疑按序：SL1/SL2 换 dash 种子（`source_lock` 改 → `e6e55c3a`→`902bb64e`）、
     `xos_profile.h`/`jobs_xos.c` SL2 改动、newlib spawn/execve hunk。
- **未运行（环境）**：dash_b/dash_c3（发版级资格测试，需 make/sbase/release 发行物，
  worktree `.cache` 无种子）；cpython_*、gcc_seed、threading_*（需大体积种子下载）；
  Qt6/aurora/ssg 家族（需私有系统构建与 Qt 资产）；iso_capacity_smoke（需 capacity
  探针构建）；完整发版流水线（发行材料缺失）。
- 迁移正确性对上述未运行家族的保障：统一转换规则 + `Guest` 后缀自动判别 +
  py_compile 全过 + 同模式 15 个客体测试实证（smoke 10 + 抽查 5）。

## 下一位 agent 可直接执行的下一步

- ~~裁决 sys54 契约 / 定位 spawn 洪流~~ 已完成（见上：契约已修、洪流归案 audio_service）。
  待办：① closed_stdin 回归向量二分（用 10-26 种子 `e6e55c3a` 重建 dash 对比，
  或先审 SL2 对 `jobs_xos`/`xos_profile` 的 fd 影响）；② audio_service 修复属 AU 线
  设计裁决（建议：由 supervisor 在 spawn 时传入 audio_tone 镜像 id，绕开 supervisor
  专属的 `sys_image_info`，而非给服务提权）；③ 两者修毕重跑 dash_c1 全 14 条刷新 C1 证据。
- 种子/发行物齐备的环境里跑 dash/cpython/threading/gcc 家族与发版流水线，补全迁移证据。
- 本分支与 `codex/bug_hunting_s4_fixes`（0223，本地 `9206ab7e`）均未推送——按用户
  指令暂缓 PR，待指示后一并交付。
- 不要误认：`real_mode.img`/工作盘/superfloppy 词义未变；冻结发行与报告中的
  `xos.img` 字样属历史证据，不得改写。
