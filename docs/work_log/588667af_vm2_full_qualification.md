# 588667af：VM2 完整验收与竞争测试

2026-11-10。接续 [VM2 页表原语与事务](2d8a0516_vm2_page_transactions.md)，
按标题生成新纪律编号。工作区基于远端 main `d708790`，验收尚在进行。

- 真客体测试对高地址 wait-word 分别执行超时、唤醒和临近截止时间的唤醒竞争；
  唤醒数与唯一结果匹配，返回后解除映射验证 pin 已清理。
- 在等待字仍被固定时由监督进程 kill，检查进程、页和等待资源回到基线。
- 混合页事务先保留已有 RW 页，再注入后续物理页分配失败，验证原内容、原可写权限
  和页计数不变。
- `build/vm2/full_races_foundation/report.json` 和
  `build/vm2/full_races_pages/report.json` 分别记录以上客体验证以及权限、事务、并发、
  kill 等回归；镜像和源码摘要以 `build/vm2/full_races/manifest.json` 为准。
- 第一次新增测试 `build/vm2/full_final_foundation/report.json` 失败：测试在清理
  unmap 时保留了上一请求的 RW 保护值，返回 code 16。修正测试后
  `build/vm2/full_retry_foundation/report.json` 通过；原始失败报告保留。

4096 页事务的全部 4096 个物理页分配失败位置已通过真实客体穷举，每次核对
资源和既有页面内容：`build/vm2/full_icount_sweep/report.json`，构建 ID
`d192fffad9190d07`。该镜像与最终 `build/vm2/full_limit/manifest.json` 的所有内核
源码摘要一致；差异仅为后续补充的客体和验收脚本。VM3 生命周期和公共 SDK 仍是
独立阶段。

长时穷举的第二个客体使用 `-icount shift=7,align=off,sleep=off` 加速模拟调度，
同样执行真实页分配、事务续体及资源检查；完整 QEMU 命令写入报告。截止时间、
等待/wake 竞争的结论仅使用常规时钟客体。常规时钟的独立穷举保留到位置 511 的完整日志，随后在全量加速穷举通过后主动结束；
`build/vm2/full_final_sweep/report.json` 因主动中断为 failed，不视为通过。

最终镜像 `build/vm2/full_limit_pages/report.json` 还验证了 4097 个已提交页的 unmap
返回 resources，且两端内容保持；decommit 一页后成功解除映射、计数回到基线。
跨页 copyin 输出内容和 copyout 已在同一客体验证。

最终镜像线程回归首次运行 `full_limit_foundation/report.json` 因资源检查看到 xsh
额外短命进程留下的暂时 completion=1 而失败；串口显示页和任务数已回基线。原报告与
串口保留。原样重跑 `full_limit_foundation_retry/report.json` 全部通过。默认镜像
`full_limit_default_accept/report.json` 验证私有 syscall 未开放。
最终专用镜像构建 ID `bdd111659e02560e`；其 `full_limit_vm1/report.json`、
`full_limit_pages/report.json` 和 `full_limit_foundation_retry/report.json` 均通过。
再次 fetch 后远端 main 仍为 `d708790`。文档链接、ABI 一致性和 `git diff --check`
通过；变更留在本地工作区。
