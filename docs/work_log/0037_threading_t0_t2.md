# 0037：公共线程 T0–T2 实施

2026-10-25；Codex 单 agent，独立分支 `codex/threading-t0-t2`。
基线 `9c896df90c2d589989b5888a495108b36959c684`。无覆盖既有未提交修改。
读 README/Discipline/state/xos_plan、0030/0031/0036 和 threading_contract v1；
基线 syscall 已到 37。源仓工作盘/发行和包管理、CPython/Open Adventure 未修改。

## 范围与实现

按 T0→T1→T2 实施 process/thread 拆分、共享空间与独立栈/TLS/FPU、创建事务、
join/detach/退出仲裁、单调等待及真实 pthread/newlib/C++ profile。接口/布局、
资源上限、锁序和边界见 `../threading_implementation.md`。原进程/文件 ABI 保留，
不引入 SMP、完整 POSIX 或 Python/Qt 移植。

修改范围：kernel tasks/paging 与通用生命周期头、shared thread_abi、user 架构
TLS/线程入口、SDK Client、libc FD/cwd/env/spawn/退出同步、新 profile 的 pthread/
锁/编译入口、源包/SDK 构建脚本、定向 guest fixtures/runners、README/ABI/架构/
决策/许可登记/本记录。未启动子 agent；共享构建与 guest suite 串行。

## 独立审查后的具体选择

1. 原 task_record 同时拥有页表与调度上下文，不能复制它做线程；拆分所有权，
   最终进程空间仍只销毁一次，工作线程不结束进程的子进程/会话。
2. 旧 ELF 地址区不整体收窄；新 profile 显式检查 0x70000000–0x71000000。
3. begin_exit 与真正停止并非同一时刻；最后线程增加内核退出屏障，等同伴安全
   停止才跑进程收尾。测试强制抢占在两个退出操作之间。
4. 旧 newlib 空锁/共享 reent 不能沿用；从固定源包重建，C++ 实际 gthread 后端
   和线程相关 libgcc 成员也重建，不用成功桩消掉符号。
5. FD 表只短暂 pin；对象 I/O 和整次会话 RPC 分别串行，避免全局 FD 锁跨分配/
   服务等待。不同 Client 的 request_id 全进程单调，避免超时后误取迟到回复。
6. 无墙钟时，noexcept C++ system_clock 查询无法返回 errno；0008 显式终止，
   steady_clock/monotonic cond 独立实现/验证。新 SDK 保留旧 single 产物。
7. 已回收 TID 无记录后为 ESRCH；仍存在的 detached/已有 join 者为 EINVAL，
   这同时满足有界记录和 ID 不复用。澄清已同步契约。

## 实际命令与证据

源包实际 SHA256、宿主工具版本、ABI 与例程命令见实现页。主要执行入口：

```sh
python3 scripts/build_threading_newlib.py --archive ../newlib-thread-source.tar.gz
make threading-smoke GCC_SOURCE=.cache/threading_sources/gcc-16.2.0 QEMU="$QEMU"
python3 tests/threading_native_toolchain.py --release-images ../runtime/xos-1024-images.tar.gz
python3 scripts/threading_qualification.py
```

其中QEMU使用冻结回执qemu.path记录的本机绝对路径，命令中的环境变量按该值展开。
构建/测试过程日志 `build/threading_*`，冻结副本和版本见
`../reports/threading_20261025/qualification.json`。工具 QEMU 为本机独立安装的
11.1.2；未把宿主线程/文件实现当作内核功能。每个 runner 用复制 boot image 和
专用临时工作盘，资源基线/结果/代码状态按各报告保存。

## 失败过程（已保留，不能记作通过）

- Git smart HTTP 遇 HTTP/2/低速错误；改用 GitHub API 逐对象校验恢复精确 Git
  历史/树，最终完整 fsck 通过。没有从不明快照编造基础提交。
- 初始编译器 bottle 的 as/ld 查找落到宿主。构建进程显式绑定已选择的交叉
  as/ld，仍检查版本/目标/实际工具路径，不把该环境泄漏给宿主 Clang 检查。
- 早期 FPU fixture 用 general-regs-only 编译，及机制汇编放入通用 sdk 目录，
  分别导致 GCC/第二 ISA 编译失败；改为 fixture 启用 SSE、架构代码归 arch。
- newlib 早期 configure 的 compile helper 错误处理汇编 -o；使用明确的 target
  CC/CCAS 配置从新缓存重建，最终新脚本完整通过。
- C++ bare-metal 默认配置未发现时间/TLS 退出能力；显式配置实际 SDK feature，
  清理旧配置对象并重建；缺失熵保持真实错误，墙钟边界用 0008。
- worker-builder fixture 初次传 argc=0，被既有 loader 拒绝；改为合法 argv，
  没有放宽权限或参数校验。后续用真实子进程验证线程退出不取消构造权所属子进程。
- 新 POSIX 环境表 fixture 初次缺少 feature macro，编译被拒绝；探针与 SDK
  编译 helper 统一定义 POSIX feature，未改成伪 setenv。

- Clang 的第二 ISA 代码生成拒绝 pthread_exit 的两种 noreturn 标注混用；
  定义沿用头文件首声明的属性，重新编译验证；没有跳过该检查。

- 普通 C 客体揭示 TLS 模板尺寸对齐与 TP 对齐混用：p_align=8 且模板尺寸不是
  16 的倍数时 worker 偏移错误（退出 97）。修正为模板按实际 PT_TLS 对齐取整、
  TP 单独至少 16 对齐，保留 C 探针并重跑。此前 C++ 布局通过不替代该验证。

- 原 E03 测试依赖故障日志的 pid/vector 前缀；新增 TID 曾改变该顺序。保留旧
  字段顺序并后附 TID，原故障隔离断言继续运行，未以跳过消除失败。

- 基线 Xsh 已将自动退休提示改为 [xsh]，旧 libc/persistence runner 仍只认 [sup]。
  在既有 prompt 兼容辅助函数加入两个精确事件别名，功能断言和资源检查保留。

- 原持久化 runner 写死 hello ELF 为 9128 字节；SDK 合法变化后实际为新大小。
  断言改绑定当前构建的准确 ELF 字节数，仍要求第二次启动走 present 路径并
  核对原文件内容/删除状态，不把大小任意化。

## 状态与后续

最终build`b33da3d9929ace75`、内核356412 B，35线程专项+37旧回归+6原生编译器
客体检查共78组通过，SDK/通用AArch64编译/7份许可材料检查亦通过。源码冻结后
统一suite通过，随后原生GCC/G++在同一新内核内实际编译运行并核对失败退出、
资源和源码sync；未以宿主交叉生成代替原生编译。发布images包SHA为
`a800969aaed03c601b8eb5029da8df1f4faecc5fa7f66ede28482aa65c7be25a`，仅提取候选盘。
SDK manifest SHA为`ee633a59f24a31da1ab8f302a8189c9313aa08171ff6b63735e49658b38477ed`。
公开回执只规范化本机绝对路径，并同时记录公开副本/原始日志SHA；原字节保留build/。

最终通过/失败/未运行和哈希以冻结回执为准；本记录不把早期不同 build 的结果
合称为同一次最终验收。源码/SDK 检查会拒绝陈旧回执和混合产物。

交付只准备独立 PR，不合并 main、不移动 0.0.1 标签、不替换附件。下一位在接收
PR 后可按冻结 SDK 接 T3-PY/T3-QT，压力专人另做长时间/随机调度与高水位。
CPython PY0 的 single/thread-stubs profile 没有自动变为真实 pthread。
用户锁环、robust/cancel/forced-unwind、墙钟/熵、第二 ISA/SMP、完整标准库与
新二进制发行许可材料仍是明确边界，不能据本次定向探针推出已完成。
