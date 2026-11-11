# VM1 私有探针验收

2026-11-09。VM1 仅以 `--vm1-probe` 专用镜像开放测试入口；默认镜像没有sys67实现，
SDK不声明能力。两套镜像均基于同一源码树，分别绑定各自manifest和客体探针哈希。
报告与系统manifest是路径模板化的公开派生文件；`original_hashes.json`记录原始JSON
的SHA-256，原件保留在本地对应build目录，派生文件不能冒充原件。

- `probe_report.json`：QEMU单CPU、512 MiB，系统build `77799411632cbddd`；两次
  客体进程通过4 TiB单次、8 TiB累计与超额拒绝、稀疏保留前后物理空闲页不变、
  冲突/洞/重用/分裂以及256片段耗尽回滚；每次退出后父级资源计数恢复。读取NONE
  保留区产生真实vector 14，故障进程退出后资源恢复。探针内也检查保留存在时fork和
  exec拒绝，避免在VM3前泄露不完整语义。
- `default_report.json`：系统build `9ebeaecdb6056692`；普通镜像连续两次以有效
  reserve请求调用67均被拒绝，进程退出后资源恢复，确认尚未公开能力。
- `dash_report.json`：同一探针构建的dash C2 29项通过，含真实fork内存不足回滚和多次回收；未包含线程libc fork探针。旧测试硬编码磁盘镜像名，使用独立目录将ISO以兼容入口运行，未改写原始系统manifest。
- `tests/fixtures/vm1/reservations_test.cpp` 宿主20,000次确定性混合操作与位图参考模型
  对比，另覆盖配额、错误优先级和槽满时分裂原子性；GCC address/undefined sanitizer
  通过。泄漏检测因当前执行环境的ptrace限制无法运行，重试设置`detect_leaks=0`；本
  实现使用固定数组，不以此声称完整泄漏检测通过。

串口为客体原始输出。早期交叉构建的警告和为纳入最终测试更改而中止的构建仅留在
本地构建日志；本回执只绑定最终输入。未运行提交/保护、真实文件映射、隐藏页、
多线程fork、SMP、长期压力或V2–V7；旧资格不改绑。客体探针使用test-only统计读取
物理空闲页，不能作为公共ABI，也不能替代将来VMA/页表独立计数接口。

公开报告中的 `${XOS_GUEST_ROOT}` 表示客体根目录；`${XOS_ROOT}` 和 `${XOS_TOOLCHAIN}` 是宿主路径模板。原件摘要见 `original_hashes.json`。
