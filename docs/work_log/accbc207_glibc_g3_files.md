# accbc207 — glibc G3-F files 后端与 preview SDK 验证

当前交付：完整组合 SDK 与正常/故障系统已从稳定源码重新构建，27 次常规客体
运行、1 次真实服务死亡及独立 TLS 回归均通过。最终来源绑定结果见文末。

## 范围与来源

以 PR #149 的 `6a463517bfa0d4d183c9107578c0ce582d6ed2d1` 为基线，
为静态 glibc 增加真实 files 服务、FD 生命周期、启动继承与公共文件接口。
基础公共 flag/stat 头单独提交 `42d2e19`，供 G2 完整 libc 构建使用。
随后用已安装 SDK 编译公共 probe 时发现 `include_next` 无后备头的问题，
独立修复 `095fc62` 将公开 fcntl 头改为自包含，并保留全部现有 flag 数值。
模块契约见 [glibc_files_v1](../contracts/glibc_files_v1.md)。
G2 管理 CRT/TLS/完整库构建；G3-T 管理线程；本组只追加 io 的
`xos_file_runtime` 和文件相关 wrapper、测试。最终组合验证由整合者补充到本记录。

采用 release `xos-glibc-sdk-preview` 的隔离 rootfs 工具：

| 输入 | SHA-256 |
|---|---|
| `xos-glibc-sdk-preview-linux-amd64.docker.tar.zst` | `22c851b6274a62ff1e31fd78089aea611142e92af27698018ffc1dda1e134009` |
| SDK kit | `20efd69b859a149ce16c86ad92ead6f64e19c0d15f395615e4cf1e44888a70f1` |
| glibc 2.44 源码归档 | `37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667` |

工具版本：目标 GCC 16.2.0、Binutils 2.47.20260726；宿主 GCC/G++ 14.2.0。
preview 携带 QEMU 11.1.3，区别于历史固定版本 11.1.2。
preview 既有 sysroot 用于 newlib parent fixture；文件后端和 glibc child 使用
独立候选 glibc 头、库及 CRT。

## 实现与审计结果

- 32 FD/32 open-description，使用进程私有 wait/wake 锁保护完整 RPC；dup 共享
  offset，CLOEXEC 属于 FD。console/pipe 阻塞期间保留引用并释放全局锁。
- 新增完整文件公共 wrapper、64 位元数据、真实 sync/truncate、单次短 I/O、
  stat trailer 校验和 files 错误到 glibc errno 的映射。
- 服务故障采用 5 秒单调绝对截止时间并终止旧会话，避免超时写入被重放。
  严格验证 request_id、reply 长度、成功操作形状和 metadata；关闭失败也移除 FD。
- v2 转移句柄与 v3 描述表恢复共享描述，整个表验证完成后才执行 cleanup。
  审计补齐重复 handle、重复 cleanup、FD alias 冲突和孤立字段拒绝。
- `writev` 聚合缓冲为 4096 字节，保留现有 PIPE_BUF 的一次原子提交；普通文件
  仍由 wire 3800 字节容量返回短写。加入跨两个 iovec 的精确边界回归。
- `ftruncate` 的负长度返回 EINVAL；超过现有 FAT 上限返回 EFBIG。
  printf/fread/fwrite 通过真实文件 wrapper，内部不依赖 newlib 私有状态。

## 已执行验证

```sh
python3 tests/glibc_g3_files_host.py --output build/glibc_g3_files_host
python3 tests/glibc_g3_files_host.py --sanitize --output build/glibc_g3_files_sanitize
```

两次均 **PASS：25 组 FD/协议测试 + 10 组真实 files.cpp/FatFs 测试**。
FD 测试含 6 宿主线程共 6000 次有序请求、32 FD 配额及无截断副作用、
dup/close 共享 offset、v2/v3 恢复、管道阻塞 close lease、4096 字节 writev，
以及错误序号、短 reply、非法 magic/version/status、越界 I/O、metadata、
服务死亡、时钟错误、超时、迟到 reply、send failure 的无重试校验。

真实服务测试包括独立 open offset、元数据、洞零填充、truncate、unlink 后的
旧对象身份、重建同名文件、独立 append、短 I/O/ENOSPC 注入、目录路径边界、
`/dev/null` 的保留 inode 65535、实际 16 handle 配额和全部远端描述释放。
只替换 IPC/内核边界，文件处理逻辑直接来自生产服务与 FatFs。

产物位于各 output 的 `report.json`、每案例 `.log` 和 `real_service.log`；
报告包含生产源码和 fixture 的 SHA-256。ASan/UBSan 启用 fatal 模式，全部通过。
LeakSanitizer 因运行环境的 ptrace 限制单独记 **NOT_RUN**。

目标 SDK 交叉编译验证：22 个实际 glibc 文件对象通过，使用 G2 完整 libc 的
配置头与原始 io 编译参数；产物在 `build/glibc_g3_native_objects`。
公共 `stat/stat64` 布局和 flag 编译断言通过。G2 已完成含早期本后端的探索性
`make lib`；最终组合候选的编译、链接和运行由后续 SDK 回执提供。
完整 `files_public_probe.c` 也已用已安装 glibc 公共头与修复后的 XOS 头通过
GCC 16 的 `-Wall -Wextra -Werror` 编译，包含显式 exec receiver 标记的版本。

## 客体与后续验证

交付 `files_public_probe.c`：公共 fd/stdio、7000 字节往返、3 worker（内核每进程
4 线程含 main）并发文件写，另有 `single` 模式。
`service-death` 在已打开 FD 后输出并 flush `GLIBC_G3_FILES_DEATH_READY`，
请求专用故障镜像的 `/.glibc_g3_service_death`，由服务自行 exit(86)，
验证旧 FD 和新 open 的持续 EIO、close 后 EBADF，
再输出 `GLIBC_G3_FILES_DEATH_PASS`。

`files_exec_parent.c` 通过既有 newlib SDK 编译；默认 exec 路径
`/bin/glibc-g3-files.elf`，也可通过 argv[1] 指定。child 编译须显式定义
`XOS_GLIBC_G3_EXEC_RECEIVER` 才添加 `.xos.exec` 标记，G2 CRT 不全局 opt-in。
父镜像输出 `GLIBC_G3_FILES_PARENT_READY`，继承成功输出
`GLIBC_G3_FILES_INHERIT_PASS`；验证共享 offset、CLOEXEC alias 与唯一描述清理、
最高 FD 31，以及回收后实际 16 handle 可重新占满。

本 checkpoint 的真实公共 glibc 客体、服务死亡、exec 继承和多轮内核资源基线
检查标记 **NOT_RUN**，由整合者的组合 SDK 和 guest runner 补充；真实命令、
镜像/SDK/日志哈希与最终结果须加入后续回执。宿主模拟测试不替代这些门槛。
glibc 上游完整 testsuite、动态链接、terminal、多进程出站 fork/exec/spawn、
pread/pwrite 和文件 mmap 均未在本模块验收。

下一步：将本模块叠加到独立 G2/G3-T 提交，保留 io `xos_file_runtime` 注册；
使用完整候选 SDK 编译公共 probe 和现有 SDK 编译 parent，执行私有磁盘客体
矩阵。若发现失败，追加修复与真实回执后再调整模块状态。

## 后续诊断客体闭环

使用 G2 已构建完整 libc 的公共头/CRT/库，显式前置本模块 22 个交叉编译对象，
在隔离磁盘启动 `g2_system` 镜像，执行下列诊断（尚未使用最终 fresh SDK）：

| 场景 | 实际结果 | 资源恢复 |
|---|---|---|
| 文件与 7000 字节 stdio 往返 | `GLIBC_G3_FILES_PASS checks=24 threaded=0`，exit 0 | free/tasks/completions 均为 129720/3/1 |
| newlib parent 真实 exec 到 glibc | `GLIBC_G3_FILES_INHERIT_PASS checks=54 shared_offset=10 cloexec=2 quota=16`，exit 0 | 同一基线；staging 回收 134 页，child 回收 224 页 |
| 三 worker 文件写 | 加入 G3-T 的 15 个目标对象后 `GLIBC_G3_FILES_PASS checks=30 threaded=1`，exit 0 | 同一基线；child 回收 226 页 |

诊断 ELF SHA-256：

- 单线程/继承 child：`9e50768f2ba34cbb2422f9a5bb5cb4e1d9bcf0bab08befa4876beebb5ed4cd80`。
- preview newlib parent：`39b88c69276ed6ad4e552e2b9e48c1a8b187dc7a6b4eea736428ac945db8f665`。
- 并发 child：`c9036522d86da747b32f4a906f9a04ecfdc15c847f0f69550b80d3682087dc45`。
- 系统 ISO：`c1b079a0880092fae1c1359c8cd1c62f02c75f5a890989d9bc63acb9043a23d5`。

原始串口日志位于 `build/glibc_g3_diagnostic`：
`serial.log` SHA-256 `d4a430850c47f0a11690f58564f174d678bf14751a86dab56ede7ab90e8042af`；
`exec_serial.log` 为 `d464857886dc66629e6bd858c8e049e4c541dcdafa7d37695d6831ee478eef78`；
`threaded_serial.log` 为 `3b9d53bd8e2e17411458488854e916dde08e569e2ad0be268f45284e67aa7172`。
对应 JSON 报告包含 ELF 标识和前后资源值。单线程诊断曾本地删去 pthread 路径
以先排查文件接口，正式 fixture 保留三 worker 默认路径；exec 标记只在 fixture opt-in。

最初的服务死亡框架通过 shell `kill` 实际被内核拒绝，因为 files 的 `block_access`
属于受保护服务。保留这一生产策略，新增显式 `--glibc-files-death-probe` 的私有
构建选项，仅在独立镜像为 files TU 定义 `XOS_GLIBC_FILES_DEATH_PROBE=1`。
manifest 顶层 `glibc_files_death_probe` 为 true/false，构建摘要包含该值。
测试请求精确匹配操作、只读 flags、handle/offset/length/reserved 和完整路径后，
服务自行 exit(86)。默认输出目录禁止开启该选项；普通生产 files 对象不含触发路径。

已验证默认目录拒绝测试选项、Python 语法，以及真实 SDK 编译的普通/故障 files
对象中测试标记分别缺失/存在。整合者实际启动专用故障镜像后，104 项客户端检查
通过，EIO/sticky/close/exit 0 正常，内核回收 files PID 8 的 246 页。
最初的测试 hook 尝试输出 raw 诊断，但服务本身没有 console route；该输出已删除。
harness 改为核对 READY、已观察 files PID 的内核回收 trace、客户端 PASS 的顺序，
并检查进程表和资源变化。最终完整镜像及多轮回执由整合者追加。

## 最终稳定源码与完整组合验收

已纳入 G2 的独立构建修复、安装阶段串行化、生成头依赖修复，以及 G3-T 的
cleanup LIFO 回归。以下 SDK 从新目录完整构建；程序仅链接该 SDK 的完整库，
没有前置诊断对象。使用 preview 的 GCC 16.2.0、Binutils 2.47.20260726、
QEMU 11.1.3，单 CPU、512 MiB、TCG、私有 FAT32 磁盘，serial-only guest。

```sh
python3 scripts/build_glibc_sdk.py --archive "$GLIBC_ARCHIVE" --output build/g3_files_sdk_verified --jobs 6
python3 scripts/build.py --output-dir build/g3_files_system_verified
python3 scripts/build.py --output-dir build/g3_files_death_verified --glibc-files-death-probe
python3 tests/glibc_static_guest.py --system-build build/g3_files_system_verified --glibc-build build/g3_files_sdk_verified --death-system-build build/g3_files_death_verified --output build/g3_files_guest_verified --suite all --repetitions 3
python3 tests/tls_current_guest.py --system-build build/g3_files_system_verified --output build/g3_files_tls_verified
python3 scripts/verify_evidence_index.py build/g3_files_release_summary.json
```

SDK 构建结果为 `static_sdk_built`，profile 为 `xos_glibc_static_research_v1`。
正常系统 build ID 为 `9d2c4081c07ae06c`，故障系统为 `37280600f373260b`；
两份 manifest 的完整源码集合相同，fault flag 分别为 false/true。runner 在运行
前后验证系统全部产物、当前源码集合、SDK 输入/产物、manifest 和探针 ELF 哈希。

| 验收项 | 最终结果 |
|---|---|
| G2 return/exit、TLS/errno、分配失败、512 字节 stdio、析构顺序 | 两路径各 3 次通过；状态 37/39 |
| 公共 pthread、最后线程退出、16 轮 detach、活跃线程 exit 边界 | 四类各 3 次通过；普通退出 0，边界用例按约定诊断并退出 127 |
| 文件单线程、三 worker 并发、真实跨 libc exec 继承 | 三类各 3 次通过；状态均为 0 |
| 独立故障镜像中真实 files 服务死亡 | 104 项客户端检查通过；持续 EIO、关闭后 EBADF、状态 0 |
| 旧 newlib 对照 | 同系统 malloc/printf/退出 7 与资源恢复通过 |
| sys35 当前线程控制、非法地址/身份、隔离、离开态和回收 | 独立三轮通过 |

27 次常规运行每次均精确恢复 `free/tasks/completions = 129720/3/1`。
故障客体先从进程表确定 files PID 8，再核对其内核回收事件（246 页）及客户端
完成标记；随后进程表无 files，资源严格等于 `129966/2/1`，即服务页数相加、
任务数减一、完成记录数不变。该检查同时要求客户端自身资源全部归还。

| 证据（路径相对 build/） | SHA-256 |
|---|---|
| `g3_files_sdk_verified/manifest.json` | `666236fcf91ea3af87a949ead460dd0b1c6be0a13e1438ec3e840e896a8fa595` |
| `g3_files_sdk_verified/sysroot/usr/lib/libc.a` | `8dc16a836db84fe833d042e6d19846506e7ef87408cf55b5c848e741666c9038` |
| `g3_files_sdk_verified/sysroot/usr/lib/libm.a` | `01731396e1357fb07e322a4f67cc93d444525890f22af62d9bb2aba17dd0e718` |
| `g3_files_system_verified/manifest.json` | `6a097396aba94d4c3a8d78f4850e62c0b91f8931dbede8abb6541fa4198347ce` |
| `g3_files_system_verified/xos-install.iso` | `6724fe6042c9dc0fd5f95d4de5edc1e38aa4f2128e78309118ffad3be132126d` |
| `g3_files_death_verified/manifest.json` | `5f3be0a0d8ac0b5dac25471c4fb4805c2c367689199dc1799186ffb4d52cc52b` |
| `g3_files_death_verified/xos-install.iso` | `b78f5901f768842a3f7858ae04e85505f850b026488dbda748a81babdb7be223` |
| `g3_files_guest_verified/report.json` | `884ca126fc39a86c74e6f0144ee028ac1eb8404bb05fa5bb6260d4fc39eeb862` |
| `g3_files_guest_verified/serial.log` | `d7bfe092944b06b980e3c2045d58f21c506a8977c1c074cdea77e4e2f66f5ee4` |
| `g3_files_guest_verified/service_death_serial.log` | `2f4d08a1a2b13452f33664d0788d26123aa00efcd4e9adec719b12116aee8d0c` |
| `g3_files_tls_verified/report.json` | `e7976f1ef9fb95b783f180809d1d5d803c2f3d6613dd83d8ffb07ed025935723` |
| `g3_files_tls_verified/serial.log` | `165d37f83f3934af9e14469317f0c3ca0e52d41d6b3df4e4257f0bc967036e04` |

`verify_evidence_index.py` 核对上述 12 项全部匹配。完整文档一致性检查通过
（1045 个本地链接、78 个已分配 syscall、73 个 history 来源）；公开路径检查通过。

交付边界仍按研究 profile 管理：上游完整 glibc testsuite、LSan（环境 ptrace
限制）、QMP 图形/交互回归和 dash 入口未运行；本轮使用 preview QEMU 11.1.3，
历史锁定的 11.1.2 组合待补。动态链接、glibc 出站 fork/exec/spawn、terminal、
文件 mmap、pread/pwrite 和完整 POSIX 覆盖继续按后续模块推进。
glibc 源归档哈希已固定，源签名信任仍维持 source lock 的研究状态。
活跃工作线程下正常 exit 的 libc 收尾仍是明确实现缺口；本轮测试的是有界 127
退出行为。这里的正常文件、继承、故障传播和资源回收结果均已实际执行。
