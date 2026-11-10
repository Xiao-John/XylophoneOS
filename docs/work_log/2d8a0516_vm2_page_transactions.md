# 2d8a0516：VM2 页表原语和分批事务

2026-11-10。主线基点 `d708790`；工作分支 `codex/vm2-page-transactions`。
编号按工作记录新纪律，由标题种子生成。变更仅在 VM1 专用探针镜像接入私有
sys67，不公布 SDK 能力；公开接口仍依赖 VM3 生命周期实现及独立验收。

新增高地址匿名页表原语，NONE 用内核所有的非 present 页保留内容；普通映射不能覆盖
隐藏页，空间销毁释放隐藏页。接入 commit/protect/decommit 和稀疏 unmap，使用持久
事务对象、每批最多 32 项、预检、分配回滚及发布期间同进程线程暂停。高 arena 的合法
用户页支持跨页内核复制；pin 检查覆盖进程等待输出的两个页面。带保留区的探针进程仍
拒绝 fork/exec，直到 VM3 支持复制和替换全部 VMA、隐藏页。

构建 `13d869ac9ebf01d1` 的实际 QEMU 客体报告：

- `build/vm2/pages_final_vm1/report.json`：VM1 稀疏保留回归通过。
- `build/vm2/pages_final_foundation/report.json`：9 项续体、调度、关闭及等待 pin
  回归通过，其中等待输出改用高 arena 的跨页缓冲区，并验证保护降低、decommit、unmap
  相交时返回 busy。
- `build/vm2/pages_final_accept/report.json`：真实 R 写、RW 执行、RX 写、NONE
  读/写/执行产生 page fault；RX 实际执行、NONE 内容保持、decommit 清零、跨页
  copyout、4 TiB 稀疏解除及计数恢复通过。逐个注入 128 页的物理页分配失败和三个
  页表分配失败位置，资源计数恢复基线。

镜像和源码哈希及 QEMU 参数见以上报告和 `build/vm2/pages_final/manifest.json`。
自检还直接检查 NONE/RW/RX 页表权限及页表失败回收。上述验证不是公共 ABI 或完整
V1–V7 资格；事务阶段的实际 kill 和更多并发竞态仍需继续检查。

追加验证：再次 `git fetch origin main`，远端与基点一致。最终专用构建
`3f7ce51e407263c0` 的 `build/vm2/pages_pins_foundation/report.json` 与
`build/vm2/pages_pins_accept/report.json` 均通过。后者在真实 4096 页事务暂存
64 页后和发布期间分别 kill，随后核对资源基线；前者另以实际高 arena wait-word 和
thread-join 结果缓冲验证 decommit 的 pin 冲突，并确认唤醒及结果交付。

此前对 `cd0b95be42f771aa` 并行运行的两次测试中，串口记录显示 xsh 启动了额外短命
进程，检查时 free/tasks 恢复而 completions 暂为 1；原始失败报告保留在
`build/vm2/pages_kill_accept/report.json` 和 `build/vm2/pages_kill_foundation/report.json`。
串行重跑 `pages_kill_accept_retry` 和 `pages_kill_foundation_retry` 均通过，未将失败
报告改写为通过。最终构建也按串行方式验收。

默认构建 `5ed356a7243101c4` 的 `build/vm2/default_final_accept/report.json` 验证
sys67 探针关闭。尚未完成的矩阵包括等待超时/wake/关闭竞态的组合压力，以及最大 4096 页事务所有
故障位置的穷举；当前 128 页逐点注入不能
替代这些项目。VM3 的 fork/exec 和 SDK 也尚未实现。

追加两线程真实 VM 事务验收：`build/vm2/pages_concurrent_foundation/report.json`
包含同进程同时 reserve/commit/protect/unmap，同地址 exact reserve 的单成功与碰撞，
以及其他三种操作的串行成功；同时重跑续体、pin、关闭和计数回收。
最终专用构建 `bbded319bcde6e5e` 的 `pages_concurrent_accept/report.json` 也重跑并
通过页权限、逐页注入及准备/发布阶段 kill；源码和镜像哈希记录于该构建 manifest。
