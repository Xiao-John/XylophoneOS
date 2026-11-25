# preview SDK 与 glibc 主线程 TLS 安装机制

2026-11-25。基线 `6a463517bfa0d4d183c9107578c0ce582d6ed2d1`（PR #149），
通用 TLS 扩展作为 G2 静态 glibc 启动闭环的一部分交付。全局 `state.md` 未修改。

## 输入与环境

使用用户指定的 release
[xos-glibc-sdk-preview](https://github.com/Xiao-John/XylophoneOS/releases/tag/xos-glibc-sdk-preview)，
release 指向 `498a40ce85667a72b0c79f0ce1f5c11e7690122f`。两份资产逐字节核对
release 提供的 SHA-256：

| 资产 | SHA-256 |
|---|---|
| `xos-glibc-sdk-preview-linux-amd64-kit.tar.gz` | `20efd69b859a149ce16c86ad92ead6f64e19c0d15f395615e4cf1e44888a70f1` |
| `xos-glibc-sdk-preview-linux-amd64.docker.tar.zst` | `22c851b6274a62ff1e31fd78089aea611142e92af27698018ffc1dda1e134009` |

SDK 工具：x86_64-elf GCC/G++ 16.2.0、Binutils 2.47.20260726、NASM 3.02、
GNU Make 4.4.1；QEMU 为 preview 记录的 11.1.3，仓库默认锁仍为 11.1.2。
本次使用 Linux x86-64、QEMU TCG 单核 512 MiB。无 Docker daemon，按 manifest
顺序还原校验过的镜像层，在 rootless user/mount/network namespace 中运行其
原工具；系统目录只读，工作区和临时输出可写。GNU 工具留在隔离环境内。

原 SDK 的 `xos-sdk-smoke` 在本环境通过：交叉工具审计、freestanding ELF、
配套 newlib/C++ 静态链接，以及随包 ISO 启动至 `xos64>`。内置 sysroot 保持
newlib 身份；glibc 候选另行构建。源码归档 `glibc-2.44.tar.xz` 的实测摘要为
`37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667`，
与原 `source_lock.json` 一致；原签名信任状态继续保留。

## 机制与审查范围

现有 sys35 只能为 owned building 子进程安装 FS；glibc 自己分配 TCB 后需要
当前线程安装入口。因此先登记 `process_tls_mode`，再加入第三参数为 1 的
显式模式：仅接受当前 PID、16 字节对齐、普通用户区或匿名 VM 区内至少 16
字节已映射且可写的地址。设备映射、越界、只读和未映射地址拒绝。成功同时
更新调度保存值和 FS base；失败保持二者。内核不解析 TCB/ELF，不管理运行库
自行分配的存储。默认第三参数 0 的父子权限和 building 生命周期保持。

修改涉及共享 ABI、AMD64 syscall 分派、SDK 包装及普通/线程 SDK 能力清单。
自研新代码采用 Apache-2.0；历史文件保留原声明，无新增依赖。

## 真实验证

在当前源码构建系统，再运行独立无 libc 探针：

```sh
python3 scripts/build.py --output-dir build/g2_system
python3 tests/tls_current_guest.py \
  --system-build build/g2_system --output build/tls_current
```

以上命令均在 preview SDK 环境中执行。新的测试从 manifest 核对系统源码和
ISO，使用实际共享头构建 ELF，在全新工作盘启动；不是宿主模拟 syscall。

- **PASS**：8 个无效指针、外部/owned child 身份、旧模式 self 拒绝、旧子进程
  arena/映射检查、未知模式拒绝，失败后 FS 和内核记录保持。
- **PASS**：主线程和工作线程各自安装独立 TCB；160 次 yield、两个至少 30 ms
  的抢占区间、线程 join 后主线程 FS 保持。工作线程登记 leaving 后安装被拒绝。
- **PASS**：3 次独立启动均正常退出，精确资源基线每次恢复为
  `free=129720, tasks=3, completions=1`。
- **PASS**：Python 语法检查、目标严格警告编译。该探针无 glibc/newlib 链接。

| 产物 | 标识 |
|---|---|
| 系统 build_id | `bc648970bbfc590e` |
| ISO SHA-256 | `c1b079a0880092fae1c1359c8cd1c62f02c75f5a890989d9bc63acb9043a23d5` |
| 系统 manifest SHA-256 | `81300585444e79b4249e20d1b8646e169f2cc49fdae08c69bc1a57d35af3a7d4` |
| 探针 ELF SHA-256 | `fbc8ffc81105d30b863fc88e96c79e4df27d85fe52f091aaaf0b400e551287c6` |
| 串口日志 SHA-256 | `16455998ab554f67d2bfb05ec9ce6d2bbf9e5f05e80850e314423025c2983992` |
| 测试 report SHA-256 | `e0cd604e8c625c14e6d6ad6c30dcf935f3687b6bd1e9d41238c7c0b28465d618` |

证据位于 `build/tls_current/`；完整命令、输入/工具哈希及实际 QEMU 版本写入
report。环境禁止创建 Unix socket，首次 QMP 运行失败；为 `Guest` 增加默认
保持开启的 `qmp_enabled` 参数，本测试显式关闭 QMP，只使用串口验证。未执行
QMP 内存检查。glibc CRT、完整静态库及公开线程/文件 API 的资格由后续 G2/G3
组合测试单列；它们需要当前 glibc SDK、应用和系统的重新构建。

## 后续整合

G2 合并本机制后使用真实 `TLS_INIT_TP` 调用安装 TCB。最终组合须重建并复跑
此测试及 glibc G2/G3 探针，不能沿用上面的系统摘要。新候选若运行在旧内核上，
self 安装返回失败，由启动代码明确终止。原 newlib baseline 保留用于对照。
