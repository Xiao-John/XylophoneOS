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
