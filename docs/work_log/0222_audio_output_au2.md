# Audio output AU2：用户态单音服务与 Shell 入口

## 交付

在 `codex/audio-output-au0` 完成 AU2 源码实现。`xos-audio` 用户态服务复用 sys86
命名 IPC 和普通 channel；固定版本 wire request 为 544 字节、response 为 48 字节。
服务完整校验最多 64 项的序列后才接受，时长总和最多 10 秒；最多 8 个不同 client
PID，各自一个 session，系统同时只运行一条序列。支持 capabilities、submit、status、
cancel、close，断连取消对应任务。客户端 IPC deadline 为 1 秒，超时关闭本地连接并返回
真实错误，不自动重连或重播。

沿用 AU1 两秒 PIO lease 的安全界限：supervisor 将 controller-only 权限委派给唯一音频
服务；服务不持有 PIO，每音符创建直接子 worker 并授予精确 Speaker 端口。worker 主动
release 或退出释放端口；服务退出/撤权会停止并终止活动 worker。supervisor 在服务退出后
重启它，不恢复旧 session/job。Shell 增加异步 `tone`、完整预读校验的 `melody`、
`audio status/cancel/close/start/restart`。

## 设计及修改

- `src/shared/include/xos/audio_abi.hpp`、`src/user/include/xos/audio_client.hpp`：冻结
  线协议、限额、状态、序列校验和同步 client。
- `src/user/drivers/pc_speaker.*`、`src/user/programs/audio_tone.cpp`：用户态 PIT channel 2
  音高/时长处理与短时 PIO worker。
- `src/user/programs/audio_service.cpp`：有界 session、单活动 job、取消/断连、rest、worker
  生命周期及状态管理。
- `src/user/loader/load.cpp`、`src/user/include/xos/sdk.hpp`：提供受限 child prepare
  callback 的 spawn API，使权限在子进程开始运行前授予。
- `src/user/programs/supervisor.cpp`、`scripts/user_build.py`：服务启动、授权、重启和 Shell
  命令；将服务/worker 镜像加入内嵌构建。
- `src/kernel/arch/x86_64/tasks.cpp`、相关共享 ABI 与架构/平台文件：sys82 增加 controller
  delegation，并在 controller 死亡、exec 或撤权时清理活动 worker；不增加 syscall 编号。
- `docs/contracts/audio_service.md`、PIO 契约、ABI/SDK 文档及计划文件：记录协议、权限和
  尚未取得的资格结果。

## 快速自查与证据

- 宿主 GCC 14.2.0，以项目 freestanding 和 `-Wall -Wextra -Werror -Wconversion -Wshadow`
  配置对 AU2 的 5 个 userland translation unit 做 `-fsyntax-only`：通过。
- 相同宿主配置对变更的 `tasks.cpp`、`exceptions.cpp`、`cpu.cpp`、PC Speaker 平台文件做
  `-fsyntax-only`：通过。`tasks.cpp` 使用宿主临时目录中的仅供语法检查的
  generated-header 占位文件；这不是正式目标构建。
- 临时宿主程序检查 wire size、合法频率/时长/rest、范围越界、序列总时长与项目数边界：通过；
  临时源文件和可执行文件位于宿主临时目录，未加入仓库。
- `python3 -m py_compile scripts/user_build.py`、`git diff --check`、
  `python3 tests/report_manifest_check.py`：通过；报告目录检查无失败。
- `xos-qemu-au0:11.1.3` 容器确认有 NASM 与 QEMU，但没有 `x86_64-elf-as`；执行
  `docker run --rm -v /workspace/XylophoneOS:/work -w /work xos-qemu-au0:11.1.3 python3 scripts/build.py`
  因缺少指定 assembler 失败。宿主也没有登记的 x86_64-elf 工具链。没有伪装或替代工具链。
- 正式交叉构建、客体启动、权限/worker 隔离、序列播放、取消竞争、服务死亡恢复、WAV 捕获、
  调度延迟及人工试听：未运行；AU1/AU2 均不能标记客体验收通过。

## 下一步

按 `docs/plans/audio_output.md` 恢复与 `config/toolchain.json` 一致的 NASM 和
x86_64-elf GCC/Binutils 后，先做完整 guest build，再运行资源授权与回收、协议边界、取消、
重启和 QEMU WAV 捕获定向场景。AU2 当前实现不证明 guest 中已经发声，也不证明硬实时或 PCM。
