# E08-3 压力测试报告

**结论：部分失败。** S0/S1/S3/S4 通过；S2 在 34 成员 archive 的最终链接上暴露
guest `ld` 的 `unknown architecture` 失败，不能把本次 E08-3 压力测试标为全绿。

## 修复追记（2026-10-24，0017）

以下原压力结果保留历史，不改写为全绿。用户限定仅修已显现 bug，后续压力测试由专人负责。
定位到 libc open_normalized 把已有文件大小误作初始位置，普通打开应为0，只有append
从EOF开始；错误影响SEEK_CUR与stdio缓冲seek。未修改GNU BFD或对象生成逻辑。
修复前16KiB文件位置探针实测16384而非0；修复后raw/dup/stdio/append定位通过。

新构建b1ded17e673ccffc，新Seed a983a603cb4132f7ff02bc3471978e5099e28dad7a60f8a33658358938f14479。
仅在原现场盘副本上验证：同一34成员libscale.a（原SHA256不变）最终链接成功，
产物与strip后产物均在XOS退出42；每步资源回基线，archive/start.o/链接脚本字节未改。
证据build/archive_link_regression_report.json、work_log/0017_archive_position_fix.md。
S2这一已知故障已定向修复；没有重跑S0/S1/S3/S4、重新组装S2或扩展soak，
原报告的后续测试建议不属于本次用户授权范围。

## 索引

1. [摘要](#1-摘要)
2. [环境与基线](#2-环境与基线)
3. [结果总表](#3-结果总表)
4. [S0：现有 gate](#4-s0现有-gate)
5. [S1：10 轮完整链路](#5-s110-轮完整链路)
6. [S2：规模场景失败](#6-s2规模场景失败)
7. [S3：故障与错误路径](#7-s3故障与错误路径)
8. [S4：20 轮有界 soak](#8-s420-轮有界-soak)
9. [资源与数据完整性](#9-资源与数据完整性)
10. [证据索引与复现](#10-证据索引与复现)
11. [限制与下一步](#11-限制与下一步)

## 1. 摘要

| 项 | 结果 |
|---|---|
| 平台 | QEMU 512 MiB / 单核 TCG / 临时 512 MiB FAT32 盘 |
| 系统构建 | `5276ff16bb6470b0` |
| Seed | GNU Binutils 2.47，manifest `47ddd307…` |
| S0 现有 binutils smoke | 7 组 / 32 次客体命令通过 |
| S1 10 轮完整链路 | 通过；每步资源回基线 |
| S2 34 成员 archive / 1 MiB rodata / 8 MiB BSS | **失败**：final `ld` 报 archive 成员架构不兼容 |
| S3 故障/错误路径 | 7 个场景通过；源码逐字节保留 |
| S4 20 轮有界 soak | 通过；资源无漂移 |
| 总计 | 约 503 次客体命令；S2 未解决，整体不算通过 |

一句话：**小规模重复和错误路径干净；较大 archive 的最终链接存在真实且可复现的
失败，首个报错成员在不同运行中甚至从 21 变为 0，说明不是测试对象生成错误。**

## 2. 环境与基线

- 构建：`5276ff16bb6470b0`；`xos.img` SHA-256
  `7f4e361efed1c8b40470b30bfdb859d7d95c7bea13cfbfa3504949f82b28513a`。
- Seed manifest SHA-256：
  `1673edded076b3a8e001fc538ec52a452c38d4f2a7a115e7190fbdc2f69f3ef0`；
  Seed 构建指纹 `47ddd3071e2ad7f69b8b903c51b491aa59d81ed96e173fb0f506341248af0a9e`。
- 工具：`as`、`ld`、`ar`、`ranlib`、`strip`，由 Seed 安装到临时盘 `/bin`。
- 基线资源：`[free=130359, tasks=2, completions=0]`。
- 每次命令后都重新读 `stats`；任何页/任务/完成记录漂移立即失败。
- 日常 `work_disk.img` 未使用；所有测试盘为临时镜像，S2 现场另存。

## 3. 结果总表

| 级别 | 内容 | 命令/轮次 | 结果 |
|---|---|---|---|
| S0 | 现有 binutils smoke | 32 命令 / 7 组 | 通过 |
| S1 | as/ar/ranlib/ld/exec/strip/exec ×10 | 130 命令 / 10 轮 | 通过 |
| S2 | 32 对象 + BSS/rodata，34 成员 archive，final link | 69 命令后失败 | **失败** |
| S3 | 7 个错误/诊断/截断场景 | 7 场景 | 通过 |
| S4 | 完整链路 ×20，每轮清理 | 260 命令 / 20 轮 | 通过（有界校准） |

## 4. S0：现有 gate

执行：

```sh
python3 tests/binutils_smoke.py \
  --seed-manifest .cache/xos_seed/binutils/build/47ddd3071e2ad7f69b8b903c51b491aa59d81ed96e173fb0f506341248af0a9e/manifest.json
```

结果：`PASS: 7 E08-3 groups`，32 次真实客体命令。该 gate 覆盖两轮完整链路、
archive 索引、strip、错误路径、资源回收和 sync 重启；本次重新运行通过。
报告：`build/binutils_smoke_report.json`。

## 5. S1：10 轮完整链路

每轮：

```text
as start.s -> as answer.s -> ar rcS -> ranlib -> ld -> exec app(42)
-> strip -> exec stripped(42) -> 删除 5 个输出
```

- 10 轮、130 次客体命令，耗时 **61.79 秒**。
- 每轮 10 个资源采样，全部为 `[130359, 2, 0]`；无页/任务/完成记录漂移。
- 输出 ELF 每次都返回 42；source fixtures 未被修改（S3/S4 结束后逐字节核对）。
- 结论：小规模重复、创建/删除、strip 生命周期干净。

## 6. S2：规模场景失败

生成并执行：

- 32 个唯一符号对象 `0.o`…`31.o`；
- `bss.o`：8 MiB `.bss`；
- `rodata.o`：1 MiB `.rodata`；
- `start.o` 调用 `sym0`…`sym31`、`bss_sym`、`ro_sym`；
- 逐个 `ar rcS`/`ar r` 形成 34 成员 `libscale.a`；
- `ranlib` 后：

```text
ld -T /src/app.ld -o /out/s/scale.elf /out/s/start.o /out/s/libscale.a
```

失败输出（节选）：

```text
/bin/ld: unknown architecture of input file `/out/s/libscale.a(21.o)' is incompatible with i386:x86-64 output
/bin/ld: unknown architecture of input file `/out/s/libscale.a(22.o)' is incompatible with i386:x86-64 output
...
/bin/ld: unknown architecture of input file `/out/s/libscale.a(rodata.o)' is incompatible with i386:x86-64 output
[wait] kind=exited code=1
```

重要观察：

1. **对象本身没有坏。** 宿主检查 `21.o` 是合法 ELF64 x86-64 REL；
   `readelf -h` 正常；archive 中 34 个成员都有 ELF magic。
2. **guest `ar t` 列出全部 34 个成员**，说明 archive 头部可读。
3. **guest `ld -r -o /out/s/21r.o /out/s/21.o` 成功。**
4. **guest `ld -r -o /out/s/allr.o /out/s/libscale.a` 成功**（不拉取成员内容）。
5. **最终带 `-T` 的 `ld` 失败**；同一 archive 的第一次运行从 `21.o` 开始报，
   保留现场后的 probe 中从 `0.o` 开始报。首个失败成员不稳定，说明不是
   “第 21 个对象生成错了”，而是 final link 读取 archive/成员的路径有问题。
6. 失败没有改变资源基线；这是数据/读取路径问题，不是简单 OOM/泄漏。

现场证据：

- `build/e08_3_stress_last.img`（512 MiB，失败时的临时盘；SHA-256
  `9cc1e1b988b1dedfe806ec52aee64ef3c9a4461034b64103622fe180b7f89868`）
- `build/e08_3_stress_s2_libscale.a`（1,075,030 字节；SHA-256
  `ed73e1f4f1ab670c31fce7175a00d49356a508407c6e66345fb2e7bff9883a56`）
- `build/e08_3_stress_s2_21.o`（704 字节；SHA-256
  `63a2779a838903f4d3d8c06b0a11e97eab4159cb7de9a2d5b537551073b73787`）
- `build/e08_3_stress_s2_readelf.txt`、`build/e08_3_stress_s2_probe.txt`
- 原始错误：`build/e08_3_stress_s1s2.json` 的 `error`。

### 初步判断（未修复）

不是“as 生成 21 号对象错误”，也不是“archive 头部损坏”。需要继续隔离：

- guest `ld` 的 archive member 读取/seek/cache 路径，特别是 final link 需要
  成员 section 内容时；
- 与文件服务 read/seek 返回长度、42 个成员的文件偏移和 bfd 缓冲的关系；
- 是否只在带链接脚本/多成员 final link 时触发。

在修复前，**不能宣称 E08-3 可承载大 archive，更不能把它作为 GCC 的 archive
输入保证**。

## 7. S3：故障与错误路径

执行 7 个场景：

| 场景 | 期望 | 结果 |
|---|---|---|
| `as bad.s` 语法错误 | 非零 + 可见诊断 | 通过 |
| `as unresolved.s` | 汇编成功，留下未定义符号 | 通过 |
| `ld unresolved.o` | 非零 + `deliberately_missing_symbol` | 通过 |
| `ld -o start.o start.o libanswer.a` | 同输入/输出拒绝 | 通过 |
| `ld --plugin no_plugin.so` | 明确 unsupported | 通过 |
| `ld` 输入 32 字节截断对象 | 非零，不崩溃 | 通过 |
| `sync` | `[files] sync=ok` | 通过 |

每个正/负路径后资源回到 `[130359, 2, 0]`；fixtures 导出后逐字节一致。
未执行：kill 中途工具、磁盘满、管道反压；这些在计划中，但本次没有跑。

## 8. S4：20 轮有界 soak

- 同一完整链路 ×20，每轮删除输出；耗时 **123.10 秒**。
- 20 个资源采样全部 `[130359, 2, 0]`；无漂移。
- 这是**有界校准**，不是计划中的 100–200 轮长 soak；不能据此宣称长期稳定。

## 9. 资源与数据完整性

| 项目 | 观察 |
|---|---|
| 基线 | `free=130359, tasks=2, completions=0` |
| S1 10 个采样 | 全部与基线一致 |
| S4 20 个采样 | 全部与基线一致 |
| 源码 | S3/S4 后逐字节比较通过 |
| 产物 | 小规模 ELF 均执行返回 42；S2 未产出 |
| 失败清理 | S2 失败后资源回基线；现场盘保留 |

## 10. 证据索引与复现

- 合并数据：`build/e08_3_stress_combined.json`
- S1/S2 原始 JSON：`build/e08_3_stress_s1s2.json`
- S3/S4 原始 JSON：`build/e08_3_stress_s3s4.json`
- S0：`build/binutils_smoke_report.json`
- 串口：`build/binutils_stress_serial.log`、`build/s2_probe_serial.log`
- 新增 harness：`tests/binutils_stress.py`（未提交）

复现：

```sh
# S0
python3 tests/binutils_smoke.py --seed-manifest <seed>/manifest.json

# S1 + S2（S2 预计失败）
python3 tests/binutils_stress.py --seed-manifest <seed>/manifest.json \
  --skip-s4 --keep-image

# S3 + S4（跳过 S2）
python3 tests/binutils_stress.py --seed-manifest <seed>/manifest.json \
  --s1-cycles 0 --skip-s2
```

## 11. 限制与下一步

- 本报告只覆盖 **E08-3 binutils Seed**；不覆盖 GCC/G++、C++、TLS、完整 POSIX、
  SMP、真机或任意掉电。
- S2 是真失败；S0/S1/S3/S4 通过不能抵消它。**E08-3 压力测试不算全绿。**
- S3 未跑 kill/disk-full；S4 仅 20 轮，不是 100–200 轮。
- 下一步优先级：
  1. 隔离 S2：固定 archive、比较 20/21 成员、检查 guest `ld` 的 read/seek/
     archive member 路径，补回归；修复前不扩大 GCC archive 依赖。
  2. 补 kill 中途 `as`/`ld` 和磁盘满场景。
  3. S2 修复后重跑 S1/S2，再扩展 S4 到 100 轮以上。
  4. 通过后再开始 E08-4 的 archive/大项目压力；当前 S2 结果应作为 GCC 前 blocker。

*报告生成：2026-10-24；测试环境为固定 QEMU/TCG/临时盘，宿主 readelf 只做静态检查。*
