# ISO 安装介质计划：从 no-emulation 启动到可安装镜像

2026-10-26更新：A0–A4已完成，0047完成受限容量扩展A5；当前实现和证据见
[0047工作记录](../history/boot_display.md#log-0047_iso_capacity)。旧A0/A1探针结论仍作为历史保留。

## 当前容量与路径

默认仍为BIOS El Torito no-emulation；小boot image只含boot/loader，kernel与
可选dash分别为ISO根目录的`KERNEL.BIN`/`DASH.ELF`。ATAPI/ISO9660在loader内，
不依赖BIOS的CD读LBA，也不要求引入UEFI。

| 项目 | 当前预算/布局 | 本组实际证据 |
|---|---|---|
| kernel文件 | 8 MiB | 真链接5,603,388字节，额外5 MiB只读节全字节核对 |
| kernel内存 | 16 MiB，自1 MiB起 | 末端0x68d000，跨4 MiB |
| 初始页表 | 前18 MiB细粒度4 KiB页，保留W^X | 高rodata实际PTE R+NX |
| boot payload | 32 MiB起，最大32 MiB | 2,097,485字节RAM/安装后全哈希一致 |
| payload寿命 | 规范化descriptor，原位保留，allocator预留实际页 | bitmap逐页检查 |
| 安装 | 小缓存分块staging/commit，已有dash不覆盖 | 原生dash交互/退出、落盘全哈希 |

`boot_info.reserved`现在传24字节magic/address/size descriptor；BIOS实例放
0x6900，通用kernel不接收BIOS原始结构。原先0x2ffff8长度头、0x300000载荷、
1 MiB kernel拷贝缓存属于0040历史，不再是当前布局。sys_boot_payload仍为53，
只允许bootstrap supervisor按offset读取。

容量专项10/10、正常kernel/legacy兼容4/4、受影响通用源3个AArch64对象编译
通过；未重跑旧压力，未做真机/UEFI/任意掉电。8/16/32 MiB为预算，不能把预算
说成所有边界和全部硬件均已实测。默认旧floppy/embedded ISO仅在kernel仍满足
其512 KiB/4 MiB边界时生成；大kernel只走file-backed ISO。

## 方案比较

| 方案 | 做法 | 容量 | 代价 | 结论 |
|---|---|---|---|---|
| A. loader 读 ISO | 自写 ATAPI PIO + 最小 ISO9660，读 kernel/dash | ISO 大小 | 新启动子系统，工作量中 | **推荐** |
| B. El Torito 硬盘仿真 + RAM disk | ISO 放 FAT 镜像，BIOS 仿真，loader 读入内存 | RAM | 需要 ramdisk 块后端 | 过渡，不先做 |
| C. 2.88 MiB 软盘仿真 | 只把 1.44 翻倍 | 2.88 MiB | 仍非安装介质 | 不采用 |

## A 阶段拆分

- **A0（已通过）**：独立探针用 ATAPI PIO 读 CD 的 PVD，证明客体侧可以不依赖
  BIOS 读 ISO。没有改现有 `xos.iso` 启动路径。
- **A1（已通过）**：最小 ISO9660 单层目录查找，读出 `KERNEL.BIN`、`DASH.ELF`；
  支持多扇区文件（测试用 2100/5000 字节）。
- **A2（已通过）**：loader 从 ISO 读 `KERNEL.BIN` 并直接装入 1 MiB；
  `xos-install.iso` 的 boot image 不含 kernel，`make run` 默认使用它。
  `tests/iso_file_kernel_smoke.py` 通过。
- **A3（已通过）**：dash 安装负载从 ISO 交给 files 服务，见0040。
- **A4（已通过）**：ISO 构建器写文件清单、哈希和安装元数据，见0040。
- **A5（0047已通过）**：kernel/页表/payload容量扩展、原位预留、流式安装与
  越界拒绝；10项容量专项和4项正常兼容通过。

## A0 验收（已通过）

- 独立 `tests/fixtures/cd_probe/` 启动镜像，经 QEMU `-cdrom` 启动；
- ATAPI PIO 读取 ISO 的 PVD（LBA 16），串口打印 `CD001`；
- 失败时打印 status/error，不静默继续；
- 不修改 `xos.iso`、boot sector、loader 或 kernel 的现有路径。

证据：`tests/cd_atapi_probe.py` 构建临时 ISO 并启动，串口输出
`CDTEST ok: CD001`；报告 `build/cd_atapi_report.json`，ISO SHA256
`c5db4641…`。次要发现：no-emulation CD 上 BIOS `INT 13h AH=42h` 返回 `ah=01`，
所以 A0 走 ATAPI PIO，而不是 BIOS 读盘。

## A1 证据（已通过）

- `tests/fixtures/cd_probe/iso_stage.asm`：ATAPI 逐扇区读 PVD、根目录记录，
  匹配 `KERNEL.BIN;1` / `DASH.ELF;1`，按 extent/size 读取并校验首尾字节。
- `make_iso.py --file NAME=PATH`：在根目录写入文件记录和数据区。
- `tests/cd_iso9660_probe.py`：镜像含 2100 字节 KERNEL 和 5000 字节 DASH，
  串口输出 `A1 ok KERNEL=2100 DASH=5000`；报告 `build/cd_iso9660_report.json`。
- 限制：只支持单层根目录、`;1` 名称、单 extent、<64 KiB；未做路径表遍历、
  长名、Joliet、多 extent、文件 >64 KiB，也未把 kernel 装到 1 MiB 以上。

## 风险

- ATAPI 端口/主从盘假设：QEMU `-cdrom` 的 IDE 位置需实测，探针应明确失败。
- PIO 轮询、DRQ/ERR、2048 字节块边界和超时；不能忙等永不返回。
- 真实硬件/不同 BIOS 的 CD 行为未验证；A0 只证明当前 QEMU 基线。
- ISO9660 目录、长文件名、大小端和多 extent 在 A1 才处理。
- 分块装载到 1 MiB 以上需要 unreal mode 或保护模式复制，A2 单独验收。

## 下一步

按release新快照统一冻结与打包；容量probe和测试trailer不进入正式发行。
后续按真实需求增加安装器/认证或ISO目录能力，不能借本轮宣称通用光盘安装器。
