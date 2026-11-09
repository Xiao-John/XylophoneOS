# VM2 基底受限验收

2026-11-09，探针系统build `191de8c84bdf1b58`，默认系统build `070e1ae0898a3091`。
QEMU单CPU、512 MiB、独立FAT工作盘。完整源码/工具/产物摘要见对应派生manifest；
原始JSON的SHA-256在`original_hashes.json`，原件留在本地build目录。公开报告是路径
模板化派生文件：`${XOS_ROOT}`、`${XOS_TOOLCHAIN}`表示宿主根，`${XOS_GUEST_ROOT}`
表示客体根；它们不是原件的字节副本。

- 客体基底九项：等待word的pin和释放、进程等待结果跨页且就绪未交付时仍pin、
  同进程竞争线程暂停、分批完成时统一单调时钟前进、注入第48页失败后回滚、准备和
  发布两阶段取消、父进程取消时子进程先取消、无其他可运行进程时的时钟推进；
  各场景均核对退出后资源基线。探针以最多32页为一批分配/释放，模拟发布，不修改PTE。
- 同一探针构建VM1客体三项和dash C2 29项通过，含fork ENOMEM回滚。dash原测试使用
  旧镜像名，以隔离目录适配到本次ISO；原系统manifest未改写。线程机制probe包含
  wait/join/pin路径。默认镜像以有效请求验证sys67未公开，两次均通过。
- 宿主continuation与pin边界测试通过ASan/UBSan，`detect_leaks=0`；环境下的
  LeakSanitizer无法工作，不声称其通过。串口是客体原始输出。

本资格只覆盖续体框架、现有等待路径pin和模拟资源生命周期，不是VM2的commit、
protect、NONE/decommit、PTE发布或完整V2/V4/V5资格；也未覆盖SMP、多线程fork、
任意中断注入或长期压力。专用探针使用既有VM1测试构建开关，默认镜像不开放探针。
