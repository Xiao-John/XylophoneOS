# 0012：E08-1 存储、会话与大 ELF

状态：受限实现完成（2026-10-24）。目标为冻结基线下的真实存储/装载 gate，不进入 binutils/GCC。

## 文件责任

- 主 agent：宿主创建/安装工具、构建和测试集成、所有共享状态文档，统一构建。
- kernel Luna：src/kernel/arch/x86_64/tasks.cpp、src/kernel/core/memory.cpp、src/kernel/include/xos/memory.hpp、src/shared/include/xos/process_abi.hpp。
- files Luna：src/shared/include/xos/file_abi.hpp、src/user/include/xos/file_client.hpp、src/user/sdk/file_client.cpp、src/user/services/files.cpp、FatFs 配置及 ASCII LFN 适配。
- loader Luna：src/user/loader/、src/user/include/xos/elf.hpp、src/user/include/xos/sdk.hpp、src/user/programs/supervisor.cpp（仅装载入口）。

任何交叉修改先协商；子代理不运行构建，不修改共享文档。

## 2026-10-24 收口

状态：**E08-1 受限实现完成**。主 agent 统一集成、测试及文档，三个 Luna 分别实现
内核/文件/装载器。没有并发构建，没有修改/递归扫描 localpilot，没有读取 token，
没有创建提交或推送。Git HEAD 基线 68c3b8a（完整值见许可证基线清单）。

阶段判断：存储/文件会话 → 进程/libc → binutils → C → C++ 的依赖合理；
资源值是待真实 Seed 复核的预算，不能拿宿主 Mach-O 体积作运行证明。
异常/RTTI/TLS 是项目兼容目标，非任意 G++ 的强制前置。见 e08_storage_and_sessions.md。

## 实际改动

- kernel tasks.cpp：8 个可信文件会话，独立端点/真实 sender PID；端点 token 单调
  不复用；构造/退出/取消回收队列；拒绝向死接收者发送；保护 files bootstrap 服务。
  memory.cpp/memory.hpp/process_abi.hpp：512 MiB 管理上限、65536 页预算、完整 usable
  页与扫描提示；现有 paging_init 随上限扩展，不额外混入固件或 ISA 分支。
- 文件 ABI v2、file_client、files：路径/LFN/目录/分页、每会话句柄与生命周期、
  磁盘流式 staging、全局一笔保存互斥；FatFs 对象锁拒绝读写/别名冲突。
  fatfs_unicode.cpp 只提供 ASCII 转换，原上游 FatFs 条款保留。
- elf.cpp/load.cpp/elf.hpp/sdk.hpp：reader 校验、4 KiB 按页读取、读锁固定版本、
  BSS 清零和失败回滚；supervisor exec-file/spawn-file 不再整文件读入。
- file_ui：cat 分块输出、ls 分页与路径、mkdir/mv；保留原编辑器上限。
- make_work_disk.py：显式 FAT32 512/2048 MiB 稀疏卷，旧 FAT16 测试/已有盘保持；
  不再提供覆盖已有盘的 force 路径，临时目录和排他 link 防止误删既有 .tmp 文件。
- work_disk.py/work_disk_host.cpp：离线安装/导出，复用 FatFs，常规文件/锁、拒绝覆盖。
- user_build.py：磁盘专用 e08_probe（不嵌入启动镜像），FatFs ASCII 适配与 SDK 声明导出。
  build.py：源指纹增加 .c/.h 与 LICENSE/NOTICE/licenses 材料，全部产物有实际哈希。
- e08_storage_smoke.py 与旧用例适配：旧 4 文件/24 KiB 拒绝检查改为真实锁冲突/
  物理满盘检查；旧页上限压力改为 65536 页，旧 ELF case21 按真实上限构造。
  不能把去掉的人工限制继续写成失败条件；旧短读/EOF/错误和全部回归保留。

相关命令页/架构/SDK/工具链/README/state/decisions 已同步。代码具体文件责任在本页首部，
主 agent 另维护 file_ui、宿主脚本、tests、Makefile、许可证和文档；后续跨模块修改已汇总。

## 集成发现并修复的问题

1. 初轮仍使用 64 页共享 ABI，大 ELF 正确拒绝 too_large；统一为冻结的 65536 页。
2. PID 绑定不足以避免端点槽复用的迟到回复，改为单调不复用 token；服务存活检查、
   死接收者拒绝及 files 的 kill 保护一并补齐。
3. 不同活会话原本可重置他人的 staging，改为 busy；死会话只能由可信 PID 枚举清理。
4. 重用 staging_path 未补 NUL，短路径可能保留长路径尾缀；真实 gate 在 reopen
   stage13 捕获，所有路径复制显式包含 NUL，最终流式保存/导出逐字节通过。
5. 只读 seek 越过 EOF 时 FatFs 返回实际位置，但服务曾报告请求值；改用 f_tell，
   filetest 增加越过 EOF 验证。客户端拒绝越界响应长度，不静默截短。

失败记录的要点保留于此；最终 build/ 日志对应通过版本，不拿首轮失败当最终通过证据。

## 最终构建与验证

实际执行：`make smoke`、同源码 `python3 scripts/build.py` 重建、完整 manifest/
源码/全部产物 SHA-256 比较、许可证材料检查；查看真实 QEMU VGA 截图。

构建 f3c198eb5044cb15；源码 SHA-256：
f3c198eb5044cb15beb1883e6809cde4cc3db52294d0004335e75ec6616e9885。

| 产物 | 字节 | SHA-256 |
|---|---:|---|
| kernel.elf | 764320 | 5774a6414ff5ad9250f301223a0bbe7c54b736c4551caf7f849db0c03fbe4820 |
| kernel.bin | 274460 | 972776c5c3735954ad2fe45894c0bdcf9997a9f91d6758ec18888061691e3026 |
| xos.img | 1474560 | 74b77c85018cc8a88f695836982299b5cf70de594f71e72f4e5f2acff77e1931 |
| e08_probe.image.elf | 277808 | fed961ca05f96725403f12823994304e2a15d046b2ae268ed501e8ab5b7887fa |

内核范围 0x100000–0x16b000，文件 537 扇区，仍在原 512 KiB 文件/1 MiB 内存上限内。
工具：GCC/G++ 16.2.0、Binutils 2.47.20260726、NASM 3.02、QEMU 11.1.2；
pc-i440fx-10.0/qemu64/TCG/单核/512 MiB，工作盘 cache=writeback。

通过：实模式 6、内核 18、E03 12、E04 13、E05 8、E07 正常重启 4、物理满盘 1、
E06 3、E08-1 9，合计 **74 组**；SDK 7 份许可材料副本与新源码标识检查通过。
ELF host ASan/UBSan、通用代码 AArch64 编译检查在原回归内；不是 AArch64 移植。
同源码重建完整 manifest 相同，全部源码绑定和产物哈希逐项一致。

E08-1 的 9 项：两容量各含大 ELF/路径/目录/流式保存/同步资源回收、非法大 ELF
拒绝、重启读回；2 GiB 另测两个活客户端独立 RPC/保存 busy、取消时打开/staging
回收、65536 页分配与完整页表撤销。导出 262144 字节逐字节匹配客体生成规则。
277808 字节探针有 2 MiB BSS，实际从盘流式装载并访问；不是只给小 ELF 加尾部填充。

最终有限性能样本：512 MiB 盘原始 ATA 8 MiB 读 1.227 秒（6.52 MiB/s），
文件服务读 2.023 秒（3.96 MiB/s）；2 GiB 盘分别 1.188 秒（6.74 MiB/s）、
1.931 秒（4.14 MiB/s）。65536 页上限/回滚约 0.396 秒。
当前不触发更换预载方案；这些是缓存/宿主负载下样本，不证明真实 Seed 足够或需 demand paging。

证据：build/manifest.json、各 *_smoke_report.json、e08_storage_smoke_report.json、
e08_rebuild_check.json、license_report.json、e08_*_serial.log、e08_2048_screen.png。
实际查看后者：第二次启动 verify 输出 BSS/path/stream/sync=ok，exited 0。

## 追加的用户决定与许可证

- 未来图形 API 优先 SDL 兼容，保留显示/输入机制与用户态适配边界；版本和子集按
  另一项目的 GUI 库需求对接，当前不做 SDL/GUI，不阻塞工具链。
- 新代码采用 Apache-2.0；历史 MIT 文本及基线文件清单保留；第三方原条款保留。
  LICENSE、NOTICE、licenses/components.json、licensing.md 以及 SDK 真实导出落实。
- newlib 不是统一 LGPL；COPYING.NEWLIB 第21/22节的 LGPL 声明标注 Linux-only。
  没有完成当前 .a 逐成员来源/许可证映射，材料检查不冒充法律兼容性全部审计。
  未来分发 GNU Seed/运行库前需按实际条款补材料，不能用 Apache 替第三方改标。

## 限制与下一步

下一组 **E08-2**：实际调用点驱动的 argv/env/cwd、spawn/wait、必要 stdio/pipe、
newlib 文件 fd/errno 映射与退出回收。先过小程序读源/写产物/启动子工具 gate，
不提前进入 binutils/GCC。

未运行/未完成：真实 Seed 运行与峰值内存、原生编译、一般子程序构造权、POSIX 文件
兼容、动态堆、C++ 运行库/异常/RTTI/TLS、Unicode、sysroot 只读授权、服务重启、
任意掉电/坏扇区/长期压力、真机、UEFI、SMP。没有测试物理掉电事务保证；日志恢复
不能替代完整 FAT 崩溃一致性。E08 整体未完成，O11–O13 仍不标通过。
