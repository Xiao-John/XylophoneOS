# 0051：E14 Display Backend / G02

2026-10-26（Asia/Shanghai）。基线upstream main 5b4e5e13a15234209cc42f1ba09d5b240cb78043，
fork main当时9c896df；隔离worktree `XylophoneOS-display-e14`，分支
`feature/display-backend-e14`。其他XOS线程/Dash任务不活跃，无覆盖/清理其源码/缓存。

## 实现与决定

D0–D4顺序推进。三条BIOS loader共用VBE探测，boot_info v2追加48字节规范化信息，
原64字节字段和ISO payload不变；支持800×600/640×480 32位直色LFB，实际探测
800×600/stride3200/1920000字节/0xfd000000。显存以专用UC RW/NX supervisor映射
绕开512MiB RAM分配器，不放宽普通物理映射权限。图形模式停用0xB8000，COM1保留。

PS/2 IRQ1/12接IDT/PIC级联/EOI，64条FIFO与明确resync丢失语义；原始键与文本分开。
现有IPC认证display服务和唯一surface；sys63/64、共享ABI/SDK，完整源缓冲预检后
批量提交dirty rect，普通用户不映射MMIO。服务撤销file/构造权限，进程身份来自内核。
客户端/服务退出、异常、成功exec清理channel/focus/等待；恢复路径是监督重新启动。
原生gfxdemo绘制木琴与键鼠反馈，显式错误/线程/OOM/异常探针；Qt不编译。
详细所有权/同步/缓存/Qt QPA映射见display_backend.md，决定同步decisions.md。

修改范围：src/boot/x86/display.inc与三个loader；kernel boot_info/paging/console/IRQ，
独立platform/pc/display.cpp/ps2.cpp与调度适配display_tasks.inc；共享display_abi.hpp、
SDK display_client.hpp、服务display.cpp、gfxdemo与Xshell启动命令；构建/SDK清单与测试。
所有新增自研源码Apache-2.0，无新增第三方依赖，不改变其许可证。

## 实际构建与验收

宿主GCC/G++16.2.0、Binutils2.47.20260726、NASM3.02，QEMU11.1.2、pc-i440fx-10.0、
qemu64、TCG、512MiB、单核、无网络。仅此worktree/build串行构建，测试临时专用FAT盘。

```sh
python3 scripts/build.py
python3 scripts/build_install_iso.py --dash-manifest build/e14_dash_manifest.json
QEMU=/path/qemu-system-x86_64 python3 tests/display_smoke.py --output build/display_delivery
# 下列入口同一源码/镜像依次运行，未跳过失败检查
QEMU=/path/qemu-system-x86_64 python3 tests/kernel_smoke.py
QEMU=/path/qemu-system-x86_64 python3 tests/process_smoke.py
QEMU=/path/qemu-system-x86_64 python3 tests/threading_smoke.py
QEMU=/path/qemu-system-x86_64 python3 tests/runtime_smoke.py
QEMU=/path/qemu-system-x86_64 python3 tests/libc_smoke.py
QEMU=/path/qemu-system-x86_64 python3 tests/file_smoke.py
QEMU=/path/qemu-system-x86_64 python3 tests/persist_smoke.py
python3 scripts/license_audit.py
QEMU=/path/qemu-system-x86_64 python3 tests/threading_native_toolchain.py --release-images /path/xos-1024-images.tar.gz
QEMU=/path/qemu-system-x86_64 python3 tests/display_compat.py --dash /path/accepted/dash.elf --make /path/accepted/make.elf --python-stage /path/accepted/stage_py1 --thread-probe /path/accepted/threading_cpp_probe.elf
```

G02 19组通过：23个显示/非法缓冲/长度/坐标/稀疏末页原子拒绝/配额/焦点检查，
全部1920000显存字节与预期相等，QEMU scanout截图核对；QMP真实PS/2键序/修饰、
鼠标位移/点击/释放、队列溢出/无焦点丢弃；双线程越权拒绝、普通MMIO #PF、
四轮客户端故障恢复、服务kill/真实#UD和在途唤醒、三轮启动停机、真实物理OOM
部分分配回滚、软盘/两种ISO和无显卡串口启动。资源基线[130323,2,0]，最终准确恢复。

原回归入口9个全部退出0；客体功能分组为kernel18/process13/threading15/runtime5/
libc3/file8/persist4/native6，共72组；另许可证7份材料完整性检查，不是法律/成员审计。
兼容5组：已验哈希固定的Dash pipeline/fork/substitution/heredoc，Make真实shell recipe，
CPython真实Lock/RLock/Condition/Event/Queue，已验C++线程profile在服务运行时执行，
带Dash payload的file-backed ISO/图形恢复。旧二进制未重建，输入摘要随报告冻结。

## 保留的失败与修复

初次runner把checks=pass汇总也计入23项前的19项计数、误认为libc_hello退出0
（实际既有契约为7）、无显卡用trace关闭却期待debug退出格式，均修正为实际契约。
并发服务日志可插入多次write的启动回执中，改成单次SDK write；一次构建因选择全局
write而拉入libc __errno未链接，明确SDK命名空间后修复。

旧kernel_smoke将页表指针当2MiB叶子检查NX，与已整合ISO容量的4KiB布局不符；
现逐层验证实际叶子NX、supervisor位与设备UC，未跳过权限检查。旧runtime_probe
仍要求WNOHANG ENOTSUP，而C3已实现，现接受运行中0或已退出child并验证真实status。
新增兼容夹具最初命名threading.py遮蔽Python标准库，改为e14_threads.py后通过。
失败回执/日志保留在build/display_attempt2、display_attempt3、display_final、
display_regression_attempt1、display_compat_attempt1及早期build日志；正式冻结仅绑定最终build。

## 冻结与边界

最终源码提交`23a3698585b291812696ccd1b6cc5913a397f22f`，build `01c8b149ecc0e4cf`。
完整来源与产物摘要、报告、客体日志、截图及压缩显存见reports/display_e14_20261026/。

- kernel.bin: SHA-256 `a26575d588cb4a69e2efa1c5411be553254ab19b9503206f6b67e60c25e296d8`
- xos.img: SHA-256 `45c852501fe821a5ee33cc781afef643206a7d2662ee41440607061a6c00c999`
- xos.iso: SHA-256 `05e86e635829f8664fb02fea04fae086d18f6b10e5d986a9a3522c94496e939b`
- xos-install.iso: SHA-256 `1d013eb61b28cde7910cf62bf7cb67140f4b90e413b3b1c3688da4164fa75652`

通过限上述QEMU配置和样本，不推导真机、SMP/抢占内核、长期/随机压力、Pause/滚轮、
640×480回退、Unicode文本/IME、多窗口、vblank/GPU、Qt或SDL实际运行；这些未运行。
Qt QPA/字体/事件循环分别继续E15/E16，不能把当前ABI存在当成Qt已移植。
旧Release/日常盘/localpilot及其他worktree未改，不合并main。PR基于当前上游main，
不再沿用历史integration分支；提交按实际功能拆分并逐批推送供维护者审查。

下一步：审查此分支与正式证据；按display_backend.md运行独立图形演示，E15补多源
事件分发，E16固定Qt版本实现QPA。没有剩余源码/构建占用。
