# ISO、显示与输入：实现摘要

截至2026-10-27。当前接口见[显示](../implementation/display.md)与[ISO](../plans/iso.md)。

## 引导与安装

- BIOS El Torito no-emulation；ATAPI PIO/最小ISO9660查根目录KERNEL.BIN与DASH.ELF。
  file-backed ISO boot image仅boot/loader，kernel直接装1MiB，不依赖BIOS CD LBA读接口。
- A0/A1是独立探针；A2实际kernel启动，A3 dash安装负载，A4清单/哈希，A5容量/边界。
- A5预算kernel文件8MiB、内存16MiB、payload自32MiB起且最多32MiB；实际验证5,603,388字节
  kernel、2,097,485字节payload，高rodata页R+NX、bitmap逐页保留、分块staging安装及全文哈希。
- boot_info.reserved传24字节规范payload descriptor；sys53仅bootstrap supervisor读取。
  旧floppy/embedded ISO仅在512KiB/4MiB边界内生成，大kernel走file-backed ISO。
- 当前工作盘make disk不预装dash；ISO携带并在首次启动安装，已有文件不静默覆盖。

容量专项10/10、正常兼容4/4及3个通用源第二ISA编译通过；正常共同build4c79f3a789dcff61。
A2早期失败和移除低端固定1MiB复制窗口的历史都不作为当前布局。真机/UEFI/任意掉电未验。

## E14/G02

- BIOS VBE XRGB8888、800×600优先，追加boot_info v2显示描述，保留payload字段；
  MMIO为supervisor RW/NX UC aperture，普通用户无权映射，图形状态停止VGA文本写，串口保留。
- PS2 IRQ1/12有界队列/丢失重同步；用户态display服务通过认证IPC管理单surface/焦点，
  用户RAM批量呈现；服务无文件/块设备/构造权，客户端/服务退出故障撤销并唤醒。
- 原生木琴gfxdemo、线程越权/边界/异常/资源回收。Qt/QPA未编译，没有GPU/窗口管理器。

原分支源码23a3698、交付f84745a、build01c8b149ecc0e4cf：G02 19组（含23边界检查、
1,920,000字节显存、QMP PS2、真实OOM、异常、三启动/无显卡）、旧72组与兼容5组通过；
输入/输出/失败/截图摘要见[冻结资格](../reports/display_e14_20261026/qualification.json)。
原分支使用sys63/64；PR #4集成改65/66并另验7组合组，见[整合摘要](delivery_audit.md)。
640×480回退、真机、SMP、长压力、Qt/SDL未验；旧原分支二进制不可混入新编号内核。

## 合并来源

原文按[source_index.json](source_index.json)记录的提交、路径和SHA256恢复；以下锚点保留旧引用。

<a id="log-0035_dash_preinstall"></a>
- `docs/history/boot_display.md#log-0035_dash_preinstall`
<a id="log-0036_iso_boot"></a>
- `docs/history/boot_display.md#log-0036_iso_boot`
<a id="log-0037_cd_atapi_a0"></a>
- `docs/history/boot_display.md#log-0037_cd_atapi_a0`
<a id="log-0038_iso9660_a1"></a>
- `docs/history/boot_display.md#log-0038_iso9660_a1`
<a id="log-0040_iso_install"></a>
- `docs/history/boot_display.md#log-0040_iso_install`
<a id="log-0047_iso_capacity"></a>
- `docs/history/boot_display.md#log-0047_iso_capacity`
<a id="log-0051_display_backend_e14"></a>
- `docs/history/boot_display.md#log-0051_display_backend_e14`
