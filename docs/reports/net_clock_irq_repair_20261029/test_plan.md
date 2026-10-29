# 实施前固定的输入与断言

2026-10-29。此计划在整改实现前写入。所有新运行使用新output，不修改旧报告/原输入断言。

1. 定向clock/IRQ客体探针：IF=0时纯EOI0/设备IRQ不得改变单调ticks；真实IRQ0 HLT后ticks严格增加，ns=ticks×10ms（有界实测）；PIC/PIT重复初始化入口不得重编程/重置；boot IRQ0不运行调度，不改变current/任务资源；进入run后sys_ticks、sys46/ns同源且不倒退；线程sleep/word deadline真实等待。
2. 平台路由探针：只认领允许且masked的独占IRQ；重复/错误owner拒绝；selected ELCR与PIC位改变/恢复，刻意改变未拥有的邻位后释放不得覆盖；cascade按真实slave剩余mask恢复。EOI无时间副作用；运行期共享设备IRQ不在本轮。
3. N1原测试全部保持：echo32字节完全一致帧（含GPU）、timeout、overflow8、jumbo5000 fail-closed、absent、quota、quota重复回收、ordinary MMIO/PCI IO拒绝、故障同boot Qt像素/文件/资源回收。旧host协议/expected值不改。
4. 旧受影响21套输入：E04原13断言（明确disposable512MiB工作盘夹具，沿用旧正式修复，不改断言）、G02 VBE19、T0/T1/T2 native/pthread/C++、file/persist、QtCore smoke/events/quota/ABI/memory/lifecycle/fault/persist/errors、QtGui pixels/input/lifecycle、Widgets/Aurora Notes interactive/lifecycle。
5. GPU原VBE/真实VirtIO paired像素、IRQ1/12键鼠实际输入；GPU+NIC共存；显式GPU quota/timeout失败后旧系统仍可用。Aurora Browser B1原离线交互/故障/回收输入复用实际ELF与原fixture，不推进网络。
6. RTC原语义独立定向：sys64返回UTC且与独立宿主时间窗口有界接近，随统一monotonic递增；无RTC/错误样本维持原失败。不得把epoch删除或把它当第二PIT计数。

每项绑定测试源码/SDK与实际ELF、镜像、QEMU命令、日志、截图（适用）、内存/任务/完成计数。
编译的原probe与断言固定来源；仅ROOT、产物/输出路径和已记录的显式工作盘夹具可适配，
适配前后源码SHA及具体变换必须保留。先前原始失败不可删，后续通过不抹除失败。

## 实际构建后的介质适配（不更改行为断言）

最新main17的FB1/FB2与原N1组合超过legacy512KiB/低4MiB窗口；现有构建器仅输出
`xos-install.iso`文件装载路线。attempt1与probe_attempt1保留，误选xos.iso的失败也保留。
所有后续运行明确optical/iso=True，实际SHA指向xos-install.iso。先运行原G02（仅主镜像
路径适配）以保留legacy-inline-ISO缺失的失败；另运行available-media子集，明确不宣称
原19组/legacy媒体通过。原Ethernet、线程、像素、权限、等待、回收断言不改。
老Qt SDK按其原源码树逐字节验证，新系统manifest另行完整验证，不改写旧SDK或资格。

## 最终构建边界与验收环境修正

C28/C26收口：原N1硬件诊断仅在显式`--net-boot-diagnostic`构建中链接；默认镜像
不含NIC驱动、其console命令或独占诊断路由状态。`--clock-irq-probe`同样仅测试。
移出无消费者的默认诊断代码后，正常镜像恢复既有floppy/inline ISO/file ISO容量范围；
最终G02将原19组及全部原媒体实跑，不能沿用先前大诊断镜像available-media子集资格。
N1和其配额失败在各自真实诊断ISO重跑，绑定不同manifest，不混用默认资格。

首次保留临时工作盘时把QMP socket也移入深层输出目录，超过macOS Unix socket104字节限制，
导致QEMU在客体启动前退出。保留该轮全部原始诊断，单独让QMP控制socket沿用短临时目录；
FAT工作盘和其fixture仍保存在本工作区。无客体断言更改。原浏览器fixture路径错误亦保留；
修正为只读原browser分支页面，页面SHA、ELF和所有行为断言不变。
