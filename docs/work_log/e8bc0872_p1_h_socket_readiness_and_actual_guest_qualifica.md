# P1-H socket readiness and actual guest qualification

2026-11-28。范围为 P1-H：连接 socket 的即时 readiness、有限 deadline、非阻塞
connect、明确的 Files/native-pipe descriptor 子集与 TCP shutdown 两个方向。
共同 state/plan 由协调线更新；本记录与报告给出本模块独立的实现和真实资格。

## 实现与接口

在既有 Net2 v2 envelope 上显式选择 capability revision 2；保留 flags=0 的
revision 1。op19 绑定只读共享页，op20 是 owned TCP read shutdown；没有新增网络
syscall。页以 session generation 和连接 handle 绑定，并用 sequence 检查一致性。
负的 poll(0) 还必须严格晚于本次调用开始采样；旧页、同一粗时钟 tick、写入中或锁
竞争返回 EAGAIN。写就绪是提示，读取后的旧正状态在同一 description 上不会残留。

共享页依赖单独的 sys88 holder-local grant release；服务/客户端均没有 manage
权限，不能用全局 revoke 代替本地释放。暂时无法释放时保留一个退休引用，清理成功
前不建立替代会话。有限 poll 扫描所有 FD 后再等 RPC，前后都复核原 description；
身份 try-lock 的 EAGAIN 在原 deadline 内重试，不把旧事件接到复用后的 FD。

生产实现按 `8fe347fc` → `6f96f9f4` → `401614a2` 交接，通用 grant 和 pipe query
保持独立依赖。涉及 Net2 ABI/SDK、service core/loop/lwIP、glibc socket/Files/poll、
构建 manifest 与对应 host/guest fixtures。详细语义见
[readiness contract](../contracts/net_readiness_pages.md)。

## 最终实际验收

[完整报告](../reports/p1_h_readiness_20261128/README.md)及平铺 manifest 保留全部
最终回执、串口、独立 packet capture、SDK/profile/系统/caller 绑定和失败记录。
普通配置 system `a84e3828dab08a67`，GNU SDK tree
`002f7b684bd7337a0d90a971ff21c0bab3654fe08fedbc0dcd544bd6b241e096`，GCC 16.2.0 /
glibc 2.44 / QEMU 11.1.3。VM/COW 和额外 fault probes 关闭。

43 项真实 guest 全通过。20 次分别观察到两线程一阻塞，再由另一线程 close 并
复用原 FD，poll 全部在 20–30 ms 返回 1/POLLNVAL，无关文件内容仍正确；每项
恢复资源。服务 PID 17/54 各自基线 [129596,3,1]，停止后均恢复 [129769,2,0]。
独立 peer 延后 SYN/ACK、保持 TCP 零窗口、核实 5840 bytes 后放开窗口；即时和
有限 poll、SO_ERROR、FIN、真实 foreign shutdown/UDP 拒绝及 owner 存活通过。
40 ms poll 在真实客体中耗时 40 ms，一秒后的只读回复只消费一次。

Host ASan/UBSan 的 socket、34 个 service 场景及 2 个 loop 场景辅助覆盖边界；
Files host regression 保留其 8 组结果。实际命令、全部 flags 和重建步骤在报告中。
LeakSanitizer 未运行，未将 host boundary injection 作为 guest 网络资格。

## 保留的失败与边界

保留同 tick 假阴性、无 manage 权限调用全局 close、clean FIN 导致 SHUT_RDWR
第二步失败、有限 poll 传播身份锁竞争 EAGAIN 的真实失败。最后一项在独立重复的
第六次真实交错中复现，并以与旧 SDK 输入哈希完全一致的旧 C 源重现 host 断言，
随后修复并通过上述 20 次普通配置客体检查。make -j8 的 GNU Versions 生成失败
也完整保留；最终 SDK 用全新目录 jobs1 构建。

额外 VM probe 开启的 `c86e685b8bf4c00b` 也通过 43 项，但单独记录，最终资格使用
普通配置。pthread_cancel 仍为 ENOTSUP；不宣称全 POSIX、GNU UDP/listen/accept、
console/terminal actor readiness、继承 stdio route 的新增组合资格、动态 GNU
运行库组合或物理 NIC。网络 RPC 的非阻塞数据操作仍有有界服务交换，不承诺 IPC
投递本身 wait-free。新 image/SDK 或后续分支整合不能直接移用本次产物资格。

下一步由协调线按独立依赖/PR 顺序交付，并更新共同 state/plan；无需继续修改
本模块已通过的输入来扩大资格。

证据检查：H 平铺索引通过，公开路径扫描 PUBLIC_READY。全仓 report manifest 检查
将 H 列为 compliant，但另有既有 17 条失败；相关目录的 Git tree 与基线 6332527
相同，未改写或将全仓结果冒称通过。完整失败与范围比较一并留存。
