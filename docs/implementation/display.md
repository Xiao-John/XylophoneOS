# E14 显示与输入后端

2026-10-26；基线 upstream main `5b4e5e13a15234209cc42f1ba09d5b240cb78043`。
D0 冻结：保留 BIOS、单核、QEMU pc-i440fx-10.0 / qemu64 / TCG / 512MiB。

## 固件与映射

选择 VBE 2+ linear framebuffer。与 Bochs DISPI 相比，BIOS 可同时取得模式、
stride、像素掩码、真实物理地址，无须硬编码 PCI BAR；不引入 GPU/UEFI。
仅接受 direct-color RGB 掩码 8:16/8:8/8:0、32bpp，优先 800×600，次选 640×480。
固件模式列表最多读取512项；失败保持文本/串口启动。引导阶段在最后一次磁盘
BIOS调用后探测、设置模式；64位内核不调用固件。

boot_info v1 的64字节布局不变，v2 size=112，在64字节后附48字节规范化显示
描述。reserved仍指向ISO payload descriptor；三种BIOS loader使用同一实现。
旧v1引导器可启动新内核；新v2引导器需要新内核，不能混搭旧内核。
固件scratch在0x7000–0x73ff；显示扩展0x6840–0x686f，在reserved_low范围内。

平台校验模式、长度和地址，专用0x30000000 aperture映射显存为supervisor RW/NX、
PCD+PWT（UC），不放入512MiB RAM页分配器，也不放宽普通map_page的物理上限。
所有进程共享supervisor-only内核PD；普通用户不能映射MMIO。映射表页为启动期
固定开销。日志/panic经COM1；VBE启用后停止读写0xB8000。

D0/D1初次真实QEMU11.1.2探测：800×600、stride3200、XRGB8888、1920000字节，
物理地址0xfd000000（来自VBE，不是源码常量）；boot/kernel/任务初始化成功。
证据build/display_probe_serial.log、build/d0.ppm，build32cb5a58a3cd71e6。
该结果只证明模式/映射和启动，不是完整G02通过。

## Qt接口依据

Qt后续通过QPlatformScreen/QPlatformWindow/QPlatformBackingStore适配，
raster backing store支持局部重绘，QWindow表示底层window/surface生命周期。
QPA无跨小版本源码/二进制兼容保证，E16必须固定Qt版本。
本轮不构建Qt或增加其依赖。

- https://doc.qt.io/qt-6/qpa.html
- https://doc.qt.io/qt-6/qbackingstore.html
- https://doc.qt.io/qt-6/qwindow.html
- https://www.qemu.org/docs/master/specs/standard-vga.html

## SDK、权限与生命周期

`display_abi.hpp` v1 为固定宽度共享布局；sys65 是窄控制/等待接口，sys66 是
服务端批量呈现机制。已有sys0–64（熵63/墙钟64）、startup/线程/文件ABI不变。SDK manifest增加
`display_extensions`，所有旧镜像目录顺序保留，新display/gfxdemo追加。
`display_client.hpp` 为无硬件依赖客户端，用户在自己的普通RAM中绘图。

监督进程 `display-start` 通过现有用户态ELF loader启动display，再以可信父子身份
授予唯一服务角色；文件端点被撤销、spawn/delegate/fork/exec构造被拒绝，服务无
块设备权。服务实际自检文件句柄0、block_info拒绝、process_create拒绝后报告ready。
不按程序名或请求自填PID授权。服务按需启动，没有GUI不阻塞系统启动。

普通应用connect取得唯一surface与独占焦点；第二次connect为EBUSY。内核建立
一对现有endpoint，request容量64、reply容量96字节；receiver/sender PID由内核
设置，单槽满返回真实错误。服务accept拿内核认证的channel/pid。普通进程不能
接收别人请求、冒充服务、直接呈现、读取设备事件或映射MMIO。

present发送48字节版本化描述（源地址、完整buffer长度、stride/format和dirty rect），
没有每像素IPC或整屏分拆为数百条4KiB消息。sys66仅接受服务角色+已接收的活跃
request handle，从内核IPC快照取得原请求和发送者地址空间，忽略用户自报身份。
内核在首次显存写入前验证全部buffer页、范围、坐标/长度溢出、格式及stride，
随后按行/物理页批量写入显存。一次完整buffer仅一次request/reply、一次批量提交。
普通RAM为WB，设备映射UC，设备写完成SFENCE后返回；没有vblank/撕裂保证。

来源buffer仍属于客户端；调用返回前需保持存活并由应用互斥保护。当前单核、
内核不可抢占，验证→复制期间其他用户线程不能运行，避免解除映射TOCTOU。
内核不跨阻塞保存待解引用的用户指针，不把buffer或显存映射给其他进程。
并发线程发送同一channel时内核拒绝在途第二个请求；SDK调用方需用线程profile
互斥锁串行化send/wait/recv。它不提供跨线程事务路由或跨进程共享buffer。

client exit/kill/fault/成功exec原子撤销channel和focus，清事件及输入状态，唤醒等待；
service退出也撤销角色及在途channel，客户端得到ENODEV，之后监督可重新启动。
失败的exec校验不会撤销旧surface。无额外动态surface页；绘图RAM按普通进程
生命周期回收，设备页表为固定启动成本，验收以启动后的资源基线比较。
服务正常stop等待回复被消费/client断开再退出，避免回复端点先被销毁。

## 输入与等待

PS/2控制器初始化有界超时/ACK检查；IRQ1/12 IDT门与主PIC IRQ2级联、从PIC
IRQ12正确开放，slave EOI先于master。IRQ只做有界读取/解码/入队和唤醒，不绘图、
分配或IPC。初始化失败保留屏幕/串口，输入中断仍masked并打印failed。

事件56字节：sequence、monotonic_ns、kind、raw set1 code、modifiers、buttons、
dx/dy/x/y、lost；press=1/release=2/mouse=3/resync=4。extended键加0x100，
shift/ctrl/alt/caps为修饰bit0–3；鼠标button bit0–2，坐标裁剪到屏幕。
64条有界FIFO满时丢弃旧队列及触发事件，用resync取代，lost累计被丢数量，
带当前坐标/按钮/修饰快照；新事件随后有序入队。消费者收到resync须清本地
按键状态并采用快照。sequence跨focus保持单调；时间来自启动PIT的10ms时钟。

无focus事件丢弃，focus变更清队列/按键/按钮/鼠标组包状态；新owner起于屏幕中心。
focus只能服务切换为当前唯一client或0。service从内核取事件，再通过IPC交client。
client `wait_input()` 与service/response endpoint等待均在内核原子检查+阻塞，
IRQ/IPC/断开唤醒，无常态轮询；没有跨源timer/文件复用等待，此部分留E15。
只支持PC set1键事件、三键相对鼠标；Pause特殊多字节序列当前丢弃，无滚轮、
Unicode布局、文本输入/IME/热插拔或USB设备承诺。键事件不伪造文本。

## 运行与可复现验收

```sh
python3 scripts/build.py
QEMU=/path/qemu-system-x86_64 python3 tests/display_smoke.py --output build/display_qualified
QEMU=/path/qemu-system-x86_64 python3 scripts/run_qemu.py --iso-file --vga --work-disk /path/private-test.img
```

客体串口执行`run`进入Xshell，`display-start`后`exec gfxdemo`，屏幕出现木琴；
鼠标移动/三键与键盘改变顶部反馈区域，Q/ESC退出，串口Xshell仍可操作。
`exec gfxdemo check`执行错误/回收检查，`exec gfxdemo stop`结束服务，`wait <服务PID>`
收集结果。`gfxdemo fault/mmio/oom/memhold/threads/overflow`和`display-start fault`
是显式验收探针；memory hold需监督kill，不用于日常启动。
自动脚本仅创建临时专用FAT盘，用QMP真实键鼠设备事件、物理显存读取与scanout
截图核对；不调用客体内部函数。失败日志保留在独立attempt目录。

## Qt QPA / SDL 对接约定

| 需要 | E14 v1对接 |
|---|---|
| screen geometry | mode.width/height，起点(0,0)，一个全屏主surface；无动态模式变更 |
| Pixel format / stride | XRGB8888小端B,G,R,X；mode.stride是设备行跨度，buffer可为独立合法stride |
| Surface ownership | connect独占；第二个client EBUSY；close/退出/成功exec撤销 |
| Raster backing store | QPlatformBackingStore持有用户RAM，绘制完成后同步present |
| Dirty region | 每个rect一请求；QRegion多个rect逐个提交，不写边界以外像素 |
| Keyboard / mouse | 定长原始事件；QPA自行做布局/文本转换，resync清按键与采用状态快照 |
| Focus | 只有唯一owner可被服务激活，focus=0停止输入/呈现并清状态 |
| Wait / wakeup | response endpoint和input wait原子睡眠；事件/断开唤醒；E15补事件循环多源整合 |
| Service lifecycle | supervisor启动/授窄角色，异常ENODEV，退出清理后可重新启动 |
| Errors | -1权限、-2格式/边界、-3队列空、-4IPC满、-5资源、-14源地址、-16已占用、-19设备/服务失效 |
| Unsupported | 未知操作EINVAL；无多窗口/GPU/alpha合成/vsync/剪贴板/IME/字体服务 |

QWindow raster全屏几何可直接映射唯一surface；destroy断开连接。E16仍须按固定Qt
源码实现QPA、字体、QWindowSystemInterface及事件分发，当前接口存在不代表Qt已运行。
SDL的CPU raster后端可复用相同mode/present/input，SDL不是Qt的前置依赖。


## 0059本地兼容整合（2026-10-27）

当前显示ABI使用sys65/66，保留已采用的熵63和墙钟64。PR #3原分支及其冻结G02报告
仍对应63/64，不能用该报告直接证明本地组合；本轮独立构建与定向结果见0059工作记录。
显示目标须以当前共享头/SDK重建；旧PR显示二进制与当前组合内核不可混用。

## E16 QtGui 消费者（2026-10-28）

真实 Qt 6.8.3 静态 xos QPA 已通过 Display Service 呈现 QPainter 图形及 FreeType 字体，
并接入 QMP PS/2 输入；显示服务/内核/ABI 未改。QPA 使用用户 RAM，锁外 wait_input、
锁内事务，disconnect 后 pthread_join；一个独占全屏窗口。见 [E16实施](../plans/qt_e16_execution.md)
及 [G04资格](../reports/qt_e16_qualified_20261028/qualification.json)。本节不改绑旧 E14 证据。

## 2026-10-29 可选 VirtIO-GPU 2D 后端

以上为保留的E14 VBE基线；新增平台后端的受限资格见
[0081](../work_log/0081_virtio_gpu_2d_qualification.md)、
[接口/所有权契约](../contracts/virtio_gpu_2d.md)。用户态Display Service与sys65/66布局不变，
合法客户端RAM仍经认证、预检、复制后提交。VBE仍受支持；modern PCI VirtIO-GPU成功
初始化时优先使用内核私有scatter backing和fenced transfer/flush。无GPU/初始化失败
回退VBE，无受支持设备保留串口；运行期设备失效不承诺透明切换或热插拔恢复。
这不是3D、Qt绘制/着色器加速、多窗口合成或通用用户MMIO/DMA接口。
