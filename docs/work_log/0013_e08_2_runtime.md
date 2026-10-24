# 0013：E08-2 进程与 libc 基底

状态：受限E08-2 gate已通过，最终绑定5276ff16bb6470b0；E08-3另见0015。
下列首次运行部分保留过程，最终结果见末尾，不以局部探针代替binutils验收。

## 范围与文件责任

- main：user/loader、user/include/xos/sdk.hpp、user/arch/x86_64/start.asm、user.ld、
  scripts/user_build.py/build.py、新探针/测试/共享状态文档。
- kernel Luna：kernel/arch/x86_64/tasks.cpp、paging.cpp（如需）、shared/process_abi.hpp。
- files Luna：user/libc/、新增 user/include/xos/libc_runtime.hpp、文件 ABI/client/service 的必要扩展。
- loader Luna：scripts/build_binutils.py、新 src/ports/binutils/ 补丁/配置材料；仅在
  .cache/xos_seed/binutils/ 构建，不改 build/sdk。

用户允许 Luna 并行，只有 main 统一构建系统。localpilot 不扫描/修改；新代码 Apache-2.0，
第三方保留原条款。不读凭据，不推送。共享接口先沟通，冲突上报不覆盖。

## 首次运行与修复

构建 `2fc851bf0a2d1404` 首次 runtime_smoke 在启动前 -2：内核将所有
`process_image_end` 以上映射拒绝，连新的 stack/startup 也无法装入。修复为
image/heap/guard/stack 四段边界分别检查，stack/startup 只接受 RW/NX。
随后构建 `c9df6360ced7e610` 实际跑到 readdir；libc 将最后一批 cursor=0
当作立即 EOF，丢弃条目，已改为消费该批后再 EOF。

构建 `db4b0e66f3c3754d` 实际执行 `python3 tests/runtime_smoke.py`，5组通过：
3次完整驱动验证文件/临时文件/seek/目录、8MiB动态堆内容、argv/env/cwd、
子工具启动/退出码收集、pipe数据与EOF、stdout文件重定向；无grant普通程序
创建子工具被拒绝且回收；离线导出确认源码、子工具产物与重定向字节一致。
每轮真实物理页、任务数和完成记录均恢复基线。原始证据为
`build/runtime_smoke_report.json`、`build/runtime_smoke_serial.log`。

当前受限 ABI：64项argv、每串255字节，4页startup承载argv/env/cwd；
32页可用栈及guard；堆保留0x60000000–0x70000000，sys29按页分配/缩回，
仍受65536页任务上限。sys28 supervisor显式授予直接子工具构造权，不继承；
30–34为有界pipe与stdio引用构造。非完整POSIX/fork/虚拟内存实现。

binutils链接调用点推动补充access/stat存在检查、有限sysconf查询；无墙钟
gettimeofday明确ENOSYS，FAT无POSIX权限/符号链接；不得假报模式保存成功。
该构建SDK已逐文件核对复制到独立快照
`.cache/xos_seed/sdk_snapshots/42278b5770358ffb3b80d02ca877b87dbe7d7cef5aeb48b24ad050107be537fe`，
manifest SHA256为目录名。只读交给binutils构建，后续SDK改变需重新绑定/链接。

E08-2 gate 的首次证据已获得；完整回归及最终版本绑定待E08-3集成统一执行。
新 `tests/binutils_smoke.py` 和 `tests/fixtures/binutils/` 由main负责，尚未
运行真实binutils，不能将已有探针提升为E08-3通过。

## 最终状态

最终构建5276ff16bb6470b0通过79组完整回归（含本组5组），另E08-3的7组真实GNU验收通过；同源重建manifest、193产物、260源码实算一致。详情、哈希与所有失败修复留在0015。

实际工具反馈又补了newlib mkstemp复用、dup共享偏移、rmdir与unlink区分、8KiB raw write分块、控制台短写、目录遍历access及真实stat/fstat身份；case别名/不同对象/rename身份也加入runtime gate。FatFs最小SFN身份字段扩展及来源/修改说明已登记，原许可保留。

接口限制以e08_runtime.md为准：pipe保留EAGAIN、waitpid无WNOHANG、file stdio按路径重开而非共享跨进程offset，无fork/mmap/TLS/墙钟/完整POSIX。不要因GNU样本通过就扩成全POSIX声明。最终GNU使用SDK快照765f556c…，早期42278/ded6/46fb快照只追溯过程。
