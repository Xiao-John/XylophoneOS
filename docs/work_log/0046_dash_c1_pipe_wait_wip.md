# 0046：dash C1 有界管道等待原语（实验分支，未验收）

## 接管声明 / 协作范围（2026-10-25）

**任务接管人：@www080327-glitch；工作分支：`feature/dash-c1-c3`。**
按上游 `integration/2026-10-25`（基线 `4c78b27c8f07eeb69145d85786660689fe2db9df`）
与 `docs/dash_port_plan.md` 正式契约，接管 **Dash C1 / C2 / C3** 的独立实现与验收。
此声明用于避免同时改同一条执行链，**不代表已获上游合并许可，不阻止维护者决定任务分工**。

预计修改范围：Dash 端口、管道/等待/进程生命周期相关内核与 ABI、libc/SDK、
隔离测试与必要使用文档。与 CPython、xypm、ISO、Qt 等其他分支可能冲突时，
先与上游协调所有权并同步最新基线；不跨范围清理或覆盖他人的改动。

**当前事实：只有 C1 的 `sys_pipe_wait` 原型已提交，尚未构建验证。C1 Shell
流水线、C2 子环境与命令替换、C3 here-document/exec/真实脚本适配均未完成。**
须先审计/修正该原型，再按 C1→C2→C3 每阶段真实客体验收；
每一阶段单独记录实际通过、失败、未运行和源码/镜像/SDK 哈希。
未经客体验证不得将状态写为 passed。开发只推送本 fork 分支，以 Draft PR
向上游通报，未经维护者确认不合并 `integration` 或 `main`。

分支 `feature/dash-c1-c3`，从上游集成 `4c78b27c8f07eeb69145d85786660689fe2db9df` 创建。
按 `docs/dash_port_plan.md` 的 C1→C2→C3 顺序实施，**目前仅提交 C1 的一项机制改动，未完成 C1**。

## 本次实际改动

- 新增 syscall 54 `sys_pipe_wait`，对合法的进程内 pipe token 或标准输入输出 pipe 路由做“检查条件并阻塞”，不修改现有 sys0–53。
- 在单核不可抢占内核临界区中校验管道是否可读/可写，然后阻塞当前线程；读写或最终 reader/writer 关闭时唤醒相应等待者。
- newlib 的直接 pipe FD 和进程 stdio pipe 路由在 `EAGAIN` 时调用等待原语后重试；普通串口无数据时保留已有行为。
- `read/write` 仍允许短读写，现有 `EPIPE` 错误仍来自底层 `pipe_write_to`。不实现 shell 管道语法、fork、自重执行或任务编排。

## 尚未运行的检验（全部 not_run）

1. 从此分支进行独立 `make build`，确认 syscall/header/newlib 接口共同编译。
2. 真实客体使用管道两端分别在两个进程中消费和生成超过 4KiB 数据，比较全部字节，不允许 busy-spin。
3. 空管道等待后 writer 写入、满管道等待后 reader 读取、关闭最后一个 writer 后 reader EOF、关闭最后一个 reader 后 writer EPIPE。
4. 多线程等待与关闭竞态、wait 与 wake 时序、pipe slot 复用、进程 kill/abort、资源计数回基线；验证串口输入/输出不回归。
5. C1 shell 多段并发管道、前台取消、stdin 路由和失败清理；之后独立交付 C2/C3 的验收。

当前会话没有 x86_64-elf GCC 16.2、NASM、QEMU 的可运行组合，且不能直接访问用户 Mac；
所以上述全部结果 **not_run**。本提交不应标注 C1 passed，也不得合并上游。
