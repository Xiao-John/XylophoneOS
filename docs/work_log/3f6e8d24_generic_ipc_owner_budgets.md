# P0 sys84–86 每主体资源额度

2026-11-27，基于 `96d75c9` 的独立后续模块。此前 generic IPC 只有 37 个共享
endpoint、8 个 name、16 个 pending connection 的全局池，一个普通进程可一直
分配到全局耗尽。sys88 已有每进程 handle 限额，不能代替 sys84–86 的归属管理。

## 实现与兼容

同一 authenticated owner PID 最多拥有 4 个双向 pair，sys84 create 与 sys86
connect 共用额度；每 PID 最多发布 2 个 name。所有检查发生在分配/copyout 前，
超额使用既有 resources 错误，失败保留输出与已存在对象。一个 pair 只按其
canonical endpoint 计数，pending/accepted/blocked 都计入。撤销、close、成功
exec 或任一 peer 死亡清除现有对象后自动恢复额度，不维护第二套可漂移账目。
非法或重复 release 不归还额度。

共享 process ABI 头公开常量；两个 SDK manifest 的生成入口从该头读取限制，
保持单一数值来源。syscall 编号、结构和 token 语义不变，旧请求达到新上限后
收到原有资源错误。源码盘点显示网络服务需要两个名字，Pumpkin/broker 同时
自建 pair 最多三组；本模块没有声称所有消费方应用已重新验收。全局池不扩大。

本机制按 PID 归属：它限制单个进程占用，不能阻止拥有创建权的进程以多个后代
分别使用额度。完整进程树、会话或用户预算是独立后续设计，不宣传为防 DoS。

## Preview 2 开发及客体验收

使用已校验的 XOS SDK Preview 2 原有常规 launcher、GCC 16.2.0、Binutils
2.47.20260726、NASM 3.02，重新构建当前源码；QEMU TCG、512 MiB、单核。
最终 build `d9527dfd4974eb89`，ISO SHA-256：
`e6f032ebfbcf1db8009ea257d7f112093b21ec76418a7b6be255740e6184b4f8`。
新镜像内 SDK 已包含常量及 manifest；threading SDK 生成代码同步，但其独立
包未在本模块重建，默认 manifest 的 guest_qualification 继续为 not_run。

```sh
python3 scripts/build.py --output-dir build/p0_quota_system2
python3 scripts/build_ipc_exec_probe.py --sdk build/p0_quota_system2/sdk --output build/p0_quota_fixture
python3 tests/ipc_exec_guest.py --system build/p0_quota_system2 --fixture build/p0_quota_fixture --output build/p0_quota_guest --repeat 3 --serial-only
```

**3 轮、12 次调用、24 个场景全部通过**，包含前模块的 exec、五种结束路径、
重启、sys88 委派及额度回归，并新增：

- direct create 与 name connect 混用达到同一额度；pending 已计费，accept 后仍计费。
- worker 真实 blocked 时仍计费；不合法 revoke/close、重复 close 不制造额度。
- 每种失败保留 sentinel 输出及原通信对象；同名幂等 publish 不额外计费。
- 父进程耗尽 pair/name 时，另一个真实 PID 仍能发布两个名字并创建 pair。
- peer close 唤醒 blocked receiver 并释放一个额度，新 token 不复用旧 token。
- peer 退出后四个旧 pair 与两个名字均撤销，原 owner 能重新建满四个 pair。
- 全部 36 个已登记 IPC worker 返回严格 broken；每次调用资源恢复
  `[129806, 2, 0]`，没有通过增加全局上限取得通过结果。

首轮 kernel 构建的局部变量触发 `-Wshadow`，修正命名后重新完整构建，保留失败
日志。公开证据：[摘要](../reports/p0_ipc_quotas_20261127/summary.json)、
[客体](../reports/p0_ipc_quotas_20261127/guest.json)。平铺 manifest 绑定公开叶子；
摘要同时保留原始与路径/行尾规范化后的哈希。

## 回滚与下一步

回退生产限制可恢复旧全局分配行为，不涉及存储格式迁移；同时撤回新 manifest
限制描述和额度断言。原有内核身份、权限收窄、exec 失效边界不能回退。
下一独立模块提供通用 IPC 绝对期限 send/receive 等待，避免服务存活却不回复时
客户端无限阻塞。sys81 压力、完整消费方应用组合、SMP 和物理硬件未在本模块运行。
