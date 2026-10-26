# 0047：ISO 容量扩展与独立构建

2026-10-26（Asia/Shanghai）。用户明确要求子代理完成ISO扩容；主端并行推进
xypm P2-1，0046外部线负责CPython PY2。ISO子代理独占本组boot/loader/layout、
boot_info/kernel_main/memory、build与ISO构建器、新增ISO测试和本记录。主端按约定
只把tasks.cpp的`extern u8 boot_payload[]`改为`extern const u8* boot_payload`，
sys53读/查询语义保持。获主端授权后，仅修改file_ui的dash缓存/安装函数，改为
分块staging。不修改包管理、线程机制、CPython或日常工作盘；不提交/推送。

## 当前交付

- file-backed ISO的kernel文件预算8 MiB，kernel内存（含BSS/栈）预算16 MiB，
  从1 MiB开始。原先512 KiB文件/前4 MiB页表约束不再控制该路径。
- loader用低地址`0x10000–0x18fff`的9张4 KiB页表覆盖前18 MiB，保持kernel
  text RX、rodata R+NX、data/BSS RW+NX、null不映射、supervisor-only。
  内核`paging_init`只补空PD项，保留这些细粒度叶表。
- payload地址32 MiB，预算32 MiB；ISO9660 extent/大小、kernel精确长度、
  payload非零/上限和实际E820可用RAM范围先验，再按2048字节块装载。根目录
  记录先检查长度/边界；ATAPI BSY/DRQ轮询有界，错误以具体BOOT_ERROR停止。
- `boot_info.reserved`指向保留低RAM中的规范化24字节descriptor：magic、物理
  address、size（各u64）。当前BIOS loader置于0x6900；它不是BIOS原始记录。
  kernel检查descriptor头、上限、溢出、与kernel不相交、实际可用RAM覆盖。
- payload保留原位，删除额外1 MiB静态拷贝；`memory_init`逐页预留实际载荷，
  sys53只给bootstrap supervisor分块复制。不把ELF/文件路径解析放进kernel。
- `install_boot_dash`使用`file::request_data_size`小缓存、begin/chunk/commit；
  失败abort，已存在dash不覆盖。删除原先必须一次装入1 MiB缓存的限制。
- build.py新增`--output-dir`与仅验收用`--capacity-probe`；超旧loader容量时明确
  不生成xos.img/embedded xos.iso，并移除该输出目录的旧兼容产物，避免误启动。
  real_mode与file-backed ISO仍生成。正常小kernel保留旧兼容路径。
- build_install_iso.py新增`--build-dir`，默认输出/清单也跟随该私有目录，检查
  kernel/payload预算及system/dash哈希。没有改发行版本号或旧release资产。

## 实际构建与验收

工具：GCC/G++16.2.0、Binutils2.47.20260726、NASM3.02，QEMU11.1.2，
QEMU PC i440fx/TCG/qemu64/512 MiB/单核。命令均在仓库根执行：

```sh
python3 scripts/build.py --output-dir build/iso_capacity --capacity-probe
python3 tests/iso_capacity_smoke.py
python3 scripts/build.py --output-dir build/iso_capacity/normal
python3 tests/iso_capacity_compat.py --output build/iso_capacity/normal/compat_final
python3 scripts/build_install_iso.py --build-dir build/iso_capacity/normal --dash-manifest .cache/xos_seed/dash/8098a3cc28ff4ce74f5b/manifest.json
```

大kernel gate使用真实链接的额外5 MiB只读section（全字节0xa5），kernel入口后
检查全部5 MiB。不是给文件末尾补零后仅观察loader文本；损坏section最后一字节
确实触发失败。测试载荷为已验dash的有效ELF加有规律的非LOAD测试trailer，
不作为正式发行dash；整文件比1 MiB大，RAM和安装后文件均做完整SHA256核对。

容量专项 **10/10通过**，`build/iso_capacity/acceptance/report.json`：

1. 5,603,388字节真实kernel启动，5 MiB section全部正确，跨4 MiB映射。
2. 真实高地址rodata PTE为R+NX，payload全部RAM字节SHA256正确。
3. allocator bitmap中payload每一页均预留。
4. 2,097,485字节payload分块安装到FAT，dash实际进入交互并退出，导出全文件
   SHA256与ISO载荷一致（含测试trailer）。
5. kernel超限/精确长度不符拒绝。
6. payload声明超32 MiB拒绝。
7. 文件extent越过volume拒绝。
8. 截断目录record拒绝。
9. 将实际客体RAM降为32 MiB后，payload目的范围不在可用RAM，装载前拒绝。
10. 已链接probe尾字节损坏拒绝。

正常kernel兼容 **4/4通过**，`build/iso_capacity/normal/compat_final/report.json`：
floppy、embedded ISO、file-backed install ISO各自进入kernel/files；普通dash
从ISO安装、实际运行/退出、sync后导出全文件SHA256匹配。新版构建器默认私有
输出与已测试显式输出逐字节相同。受影响的boot_info/memory/kernel_main三份
通用C++还通过AArch64对象编译；这仅是耦合检查，不是第二ISA移植。

## 产物与证据

- 容量probe build：`ac93c6b476f3dcff`；kernel 5,603,388字节，memory_end
  `0x68d000`；kernel SHA256
  `96e6c53df5a79901509849769e32d6a9f0c731ec10c1109cb97af89e7680a7c2`。
- 大payload SHA256
  `61717d6e8d47dca5a9786c83453b8da3ecc03a4e570d74dcb0675dcc25b701c7`。
- 大install ISO SHA256
  `42c0ab9d3654d53d3903900b3145f6f84d6eca565cd67992d0e70a5ddaa388b6`。
- 正常build：`4c79f3a789dcff61`；kernel360508字节，memory_end `0x18d000`。
  kernel SHA256
  `fc80d0a4bac28a0dae38f84f73ac7d10541e9c95b2364e5fc2538a96d9135849`。
- 正常xos.img SHA256
  `4950c4c2fb53c36ac7cf36d4b6e40954c5b36507f8fc11207b867b54520b16ee`。
- 正常install ISO SHA256
  `4e7b5351cbd8a4988423334ed50e52940b4c414b56eb1453b500bb36d9f9df76`。
- manifest、完整命令/源码哈希、串口与QMP内存/PTE/bitmap证据位于上述私有目录；
  最终范围回执`build/iso_capacity/final_receipt.json`。

构建时主端并行修改P2测试/fixture；最终核对全部src与配置/构建核心仍与正常
manifest一致。构建后变动的测试、prepare_xypm_sdk和ISO构建器默认路径修正
单独列在最终回执；不把整个仓库后来的测试哈希冒认成原build输入。共享build/
根产物未替换；独立QEMU日志在build/iso_capacity内。没有在压力中途“修成通过”。

## 限制与下一步

8/16/32 MiB是明确支持预算，本轮实际装载证据为5.6 MiB kernel与2.1 MiB payload；
未做32 MiB满预算长时间试验。仅当前QEMU PC/IDE ATAPI单CD、ISO9660根目录
一sector、普通单extent文件，未做Joliet/目录树/多extent/通用光驱或真机。
ISO清单无运行时签名/认证，既有文件不覆盖；没有交互分区安装器、任意掉电/
撕裂扇区保证、UEFI、SMP或旧全量压力。本组无新增外部依赖，新测试Apache-2.0，
第三方dash许可/源码不变；未替代全仓许可审计。

主端可复用正常build重跑本轮P2-1专项后统一汇总state/plan/decisions；下次发行
重新冻结版本与正式dash，不发布容量probe kernel或附加trailer测试载荷。容量
扩展已不再是release阻塞，release自己的版本、打包及所需新快照gate另由主端处理。
