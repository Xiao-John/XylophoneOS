# 58b24599：VM3 生命周期与 SDK（恢复中）

基线 `2b2816b`。原执行环境被替换，先前本地提交 `4370d3b`、未提交文件、
工具链和测试产物在当前环境不可访问；远端未保存该提交。依据对话中保留的
实现片段重新构造 VM3，不将旧环境的报告改绑到当前源码。

已重新实现分批复制/回滚页表、单线程 fork 续体、匿名 VMA 的 fork/exec
生命周期、公开 sys67 和受限 mmap/mprotect/munmap，并恢复 Qt 定向验收工具。
普通和探针模式的内核源文件、普通和线程模式的 libc 在宿主编译器下通过语法
检查，VM1 保留区宿主测试、ABI 和文档一致性检查通过；这些不代替构建和客体
验收。旧环境曾报告 VM2 4096 点故障注入、VM3 fork/exec/取消、两 shell、
线程 SDK、E04、T0/T1/T2 和 QtCore/Gui 定向检查通过，但原始报告尚未找回，
不得作为本次恢复代码的资格证据。旧 Qt Widgets 测试还存在 Interactium
启动和输入时序问题；完整 Qt Widgets 和 V1–V7 组合仍未验收。

当前缺少项目固定的 x86_64-elf GCC 16.2、Binutils 2.47、NASM 3.02 和
QEMU 11.1.2；需要恢复或重建这些工具后再执行新镜像与两类 SDK 验收。
manifest 的 `vm_extensions` 维持 `implemented_unqualified`，不声明 VM3 完成。
