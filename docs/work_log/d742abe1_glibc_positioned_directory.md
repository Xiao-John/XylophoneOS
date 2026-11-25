# d742abe1 — glibc G3 目录流与定位 I/O

## 范围、依赖与接口

本模块以 PR #154 的 `5984573a3a4898734f10495af2d36de5ec16c0b6` 为基础，
依赖 PR #157 的共享 FD lease、严格 files exchange 和 native SDK hook。
开发分支先接入 `8474d27`、`61c24b5`，再补 `815b5f1` 与 `cb42fe6`；
本地对应父提交为 `a7aa492`。hook 独立提交 `b136b97` 已交公共 API 模块复用，
本提交仅交付目录和定位 I/O 的跨层闭环，终端及出站进程支持分别交付。
全局 `state.md` 由主协调者统一更新。

已协调分配 files wire v2 的 op30 `read_at`、op31 `write_at`，无新增 syscall。
op2 的 `list_identity` bit12 是显式选择的扩展记录；旧 7 字节头保持可用，
新版 13 字节头包含真实 inode 与逐记录 continuation cookie。
契约、共享头、SDK 方法、SDK manifest 和 ABI 文档校验同步登记。

- `files.cpp` 在单个服务请求内执行定位读写，始终保留共享 open-description
  offset。普通 write 继续遵循 O_APPEND，write_at 使用显式位置；沿用权限、
  维护准入、洞零填充、失败回滚和短 I/O 处理。
- glibc 的 pread/pwrite/64 别名持有固定对象 lease，一次 RPC 最大读 3798、
  写 3800 字节；负 offset 返回 EINVAL，超出 FAT 上限 `0xfffffffe` 返回
  EOVERFLOW，pipe/console 返回 ESPIPE，错误不通过 seek/read 模拟。
- 目录流拥有 FD 和整个生命周期的 lease，分页使用真实目录 handle。
  实现 opendir/fdopendir/closedir/dirfd/readdir/64/readdir_r/64_r、
  rewinddir/seekdir/telldir；复用上游 scandir 排序逻辑。
- 固定公开 dirent/dirent64 为 LP64 272 字节，d_name 偏移 12、容量 256。
  返回真实 inode、类型和名称。EOF 返回 NULL 并保留进入调用时的 errno，
  调用者可先清零以与错误区分；错误返回明确 errno。
- cookie 是存活目录的恢复位置，目录未变时可重复恢复。rename 后 handle
  继续指向原目录；已删除的空目录保持旧身份，重建同名目录得到独立身份。
  并发修改目录不提供快照、恰好一次枚举或跨重新打开的 cookie 保证。
- DIR 自身使用 wait/wake 锁；等待错误返回 EIO。关闭失效 FD 不会把 lease
  重新解析成后来复用该号码的对象。共享 exchange 在公开页面前验证完整记录。

源码主要位于 `src/ports/glibc/sysdeps/xos/xos_file_directory.*`、
`xos_file_positioned.*`、公共 wrapper、files 服务与 SDK；测试位于
`tests/glibc_files_extra_host.py`、`tests/fixtures/glibc_g3/files_extra_*` 和
`tests/glibc_static_guest.py` 的 `files-extra` suite。

## 构建输入与可复现命令

使用 release `xos-glibc-sdk-preview` 的隔离工具；`XOS_SDK_RUNNER` 指向该
工具环境的启动器，`GLIBC_ARCHIVE` 指向已锁定的 glibc 2.44 归档。
目标 GCC/G++ 16.2.0、Binutils 2.47.20260726、NASM 3.02；实际 QEMU 为
11.1.3。宿主定向测试使用当前宿主 gcc/g++；完整命令保存在冻结报告中。

```sh
python3 tests/glibc_files_extra_host.py --output build/files_extra_host_qualified
python3 tests/glibc_files_extra_host.py --sanitize --output build/files_extra_host_sanitized_qualified
python3 tests/glibc_g3_files_host.py --output build/files_api_regression_qualified
"$XOS_SDK_RUNNER" python3 scripts/build_glibc_sdk.py --archive "$GLIBC_ARCHIVE" --output build/glibc_files_extra_sdk_qualified --jobs 6
"$XOS_SDK_RUNNER" python3 scripts/build.py --output-dir build/glibc_files_extra_system_release
"$XOS_SDK_RUNNER" python3 tests/glibc_static_guest.py --system-build build/glibc_files_extra_system_release --glibc-build build/glibc_files_extra_sdk_qualified --output build/files_extra_guest_release --suite files-extra --repetitions 3
"$XOS_SDK_RUNNER" python3 tests/glibc_static_guest.py --system-build build/glibc_files_extra_system_release --glibc-build build/glibc_files_extra_sdk_qualified --output build/files_legacy_guest_release --suite files --repetitions 1
python3 tests/abi_doc_consistency.py --output-dir build/files_extra_abi_release
```

SDK 从新目录完整构建，状态 `static_sdk_built`、profile
`xos_glibc_static_research_v1`。归档 SHA-256 为
`37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667`；
提取前实际通过 PR #154 的 gpgv 签名核验，主指纹
`35B17DF5752577CA0C541CEB94BFDF4484AD142F`、签名子指纹
`FD19E6D31B192EE4DC63EAD3DC2B16215ED5412A`。
复核源身份及撤销状态的材料随共享来源契约维护。

| 最终产物 | 标识 / SHA-256 |
|---|---|
| 系统 build ID | `2802101e956bea35` |
| SDK manifest | `a16f805170c3d93dccbc85880cc6ae9e7555b161375dc6cd7344f62275d43aba` |
| glibc libc.a | `8628223f62465047de25371a16b427f61cc53e2e4a31769f24e0ef4d040cd900` |
| glibc libm.a | `be126c102e6b6a4db43ff052b0d6acf7641d676814b101ea64e8a1e1b7ca65fc` |
| 系统 manifest | `a9ba35d1591a15ea97511b95e6d9022c2ac625280e07d06af7bc1d95f03887fb` |
| xos-install.iso | `00474f8148a5fa3536b6f65eadc319d1daebf2dd357c25838b4223a0dea18834` |

这些哈希引用原始 build 产物。完整源码集合、SDK 输入、ELF 标识、工具和
签名结果见 [冻结证据](../reports/glibc_files_extra_20261125/qualification.json)。
证据为路径规范化的派生导出，`derivation.json` 保存原件路径与标识，
`manifest.json` 平铺绑定导出文件；提交树作为完整性信任根。

## 实际结果

| 验收 | 结果与观察 |
|---|---|
| 真实 files/FatFs + glibc 后端宿主集成 | 8 组 PASS |
| 同组 ASan/UBSan | 8 组 PASS，fatal sanitizer 模式 |
| 既有共享 API 回归 | 36 状态机组 + 10 真实 files/FatFs 组 PASS |
| 完整 glibc 静态构建与安装 | PASS；源签名核验先于提取 |
| 定位 I/O + 目录公共接口客体 | 3 次 PASS，每次 4429 项检查，3 worker 并发 |
| 真实跨进程共享描述与目录继承客体 | 3 次 PASS，每次 child 256 轮定位 I/O，parent offset 精确为 512 |
| 既有文件公共接口客体 | 单线程、3 worker、native→glibc exec 继承各 1 次 PASS |
| ABI 文档一致性 | PASS，新增 30/31 纳入检查 |

三轮新能力每轮枚举 100 项，含 `.`、`..`、目录、UTF-8 和长名称；核对 stat
身份、跨页 cookie、EOF/errno、scandir 顺序、真实 16 handle 配额和 64 次流复用。
跨进程用例让 native parent 与 glibc child 共享同一 open-description，parent
正常顺序读取 512 字节时 child 在 4096 位置反复 pread/pwrite；同时核对旧目录
在 rename、删除并重建后仍保持身份，最后三个目录均被回收。

九次最终客体运行均精确 exit 0，`free/tasks/completions` 在每次结束后恢复
`129715/3/1`。环境为单 CPU、512 MiB、TCG、私有 FAT32 磁盘，使用现有
serial-only Guest，QMP 关闭。runner 在运行前后校验完整源码、SDK、镜像和 ELF。

旧首次源码组合 `6e7709d96aba9bd8` 的六次客体也通过；随后补入公共 API 的
native 3800→3798 短读兼容修复并重新构建 SDK。第二组合
`466726fd774f89c1` 的六次新能力与三个既有场景通过。最终补全 SDK 能力清单后
构建 `2802101e956bea35`，并重新执行上述九次；最终报告绑定最后这个镜像。

## 失败记录与未验项

早期宿主编译曾被 native dirent shim 与 FatFs DIR 同名类型干扰，已隔离头搜索
和 fixture 命名；目标 GCC 16 的 enum/整数条件警告以明确 u32 转换修复。
首次客体 runner 在启动 QEMU 前因 native parent 的 usleep 无实现而链接失败；
随后 sched_yield 探测也因 SDK 声明缺失失败。去掉非必要延迟后，parent 通过
真实文件 IPC 调度并完成并发验收。一次源码在系统构建期间变更的候选被弃用，
重新构建新候选；这些失败及首次未运行报告保留在冻结证据中。

本组未运行 LSan（ptrace 环境限制）、实机、QEMU 11.1.2、完整上游 glibc
testsuite、dash 入口及该新组合的服务死亡镜像。宿主故障注入与严格 exchange
回归已执行；实际服务死亡后续可用已有 `--glibc-files-death-probe` 系统和
`--death-system-build` runner 入口补充。目录持续并发修改期间的快照保证不在
接口范围内。终端、glibc 出站 fork/exec/spawn、文件 mmap 与动态链接各按独立
模块继续；本组跨进程 probe 的父进程使用既有 native/newlib SDK，child 使用
完整 glibc SDK，运行时头与静态库分别链接。

下一位接手者：将本提交叠在最终 PR #157 共享 API 字节上，确认 source map 与
源码一致后发布独立 PR；如合并产生代码或 SDK 输入变化，重新构建受影响产物
和定向客体。后续 process 模块将 `.xos.exec` 标记移入实际 runtime 时，移除
两个 file probe 的条件测试标记，避免同一 ELF 出现重复标记节。
