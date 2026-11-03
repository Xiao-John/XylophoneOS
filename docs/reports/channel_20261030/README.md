# 通道定向客体验收

2026-10-30，PASSED_SUBSET。实际源码提交 a2ccab12db721e25e35fb100ec3fe6bbbfa687ae，
系统 build 839914b3b056de4b；报告绑定真实镜像、SDK树、探针ELF、构建命令及QEMU命令。
无源码修复或放松断言，首次定向运行通过。父子双向收发、枚举身份、立即等待、
每控制者4通道配额、关闭旧句柄拒绝、短缓冲失败消息保留及子退出失效已执行。

通过 xsh exec-driver 显式授予父进程 spawn 权，子进程未获额外授权。
dash 本轮 NOT_RUN：探针使用旧窄SDK启动入口，未制作真实 startup-v3 libc CRT
及 dash 授权启动组合，不以 xsh 结果代替 dash 资格。

这是既有探针的有限验收，不含阻塞close、故障、fork/exec、并发、压力、全部资源
计数回归或完整W1。报告里的一个顶层检查汇总多个探针断言，不冒称多个独立套件。
主工作区正整合其他提交，未修改；此结果不改绑整合后基线。sys80/81尚未交付主线，
本结果不替代公共ABI登记合入。存量/本地驱动架构合规也没有由本探针认证。

证据：report.json、serial.log.gz、system_manifest.json、build.log.gz；
checksums.json记录最初四项。大镜像和SDK保存在本验收worktree忽略build目录。
后续本组文档提交不改变此处冻结的源码提交。原日志保留，不重写已验输入。
