# 2a68f4a2 · glibc D1 高地址布局固定工件

2026-11-26 · 以 `c75782f4` 为基线，覆盖 [D0 地址与权限](../contracts/dynamic_linking_d0.md#5-推荐启动路径与地址布局)
的一组真实行为。先使用历史已验签静态 SDK 探索，再从本轮提交构建系统和 SDK 做正式复跑。

使用 SDK 绑定的 GCC 生成 `-fPIC -mcmodel=small` 对象，再用同一工具链的 GNU `ld -shared`
生成 x86-64 `ET_DYN`。开发探针发现 bare-ELF GCC 驱动的 `-shared` 产生 `ET_EXEC`，因此
链接步骤显式使用 `ld`，宿主对产物核对 `e_type`、`PT_LOAD`、`PT_GNU_RELRO` 和单个
`R_X86_64_RELATIVE`。无依赖的固定输入生成只含该 `ET_DYN` 原始字节和对应描述的头文件，
绑定进测试用静态 glibc ELF。客体从内嵌字节复制各段，只有这一条固定的数据重定位，
普通原生 `exec-file` 入口运行静态测试程序。

客体调用 glibc `mmap(PROT_NONE, MAP_FIXED_NOREPLACE)` 和 `mprotect` 走公开 sys67。
段先以 RW+NX 复制，核对文件段尾至内存段尾全零，重定位后改为 R、RX、RW 和 RELRO。
两个高地址同时存在，入口分别操作相对指针所指的可写数据和超过一页的 BSS。再次
精确保留已映射地址返回 `EEXIST`，原对象仍可执行。释放两个区间后，原地址均可重新
精确保留。三个独立客体进程验证 RELRO 写、RW 执行和读未提交洞，逐个核对故障地址、
任务 pid、退出状态及回收计数。

```sh
python3 -B scripts/build.py --output-dir build/d1-exact-system
python3 -B scripts/build_glibc_sdk.py --archive "$GLIBC_ARCHIVE" --output "$GLIBC_BUILD" --jobs 3
python3 -B scripts/create_xypm_profile.py create --runtime-family glibc --sdk-build "$GLIBC_BUILD" \
  --id xos-x86_64-glibc-d1-layout --output "$GLIBC_PROFILE"
python3 -B tests/glibc_d1_layout_guest.py --system "$D1_SYSTEM_BUILD" --sdk-build "$GLIBC_BUILD" \
  --profile "$GLIBC_PROFILE" --output build/d1-exact-evidence
```

## 正式复跑

从 `391d432a` 构建。系统在 macOS arm64 构建，glibc 2.44 C SDK 在断网 Linux arm64
容器从 `upstream_signature_verified` 归档构建。探针前后核对系统源码、glibc SDK 源码、
SDK profile 及工件。GCC 16.2.0、binutils 2.47 的实际二进制摘要与 SDK 清单匹配。
QEMU 11.1.3，单 CPU，512 MiB，无网卡，临时 FAT 盘。公开 ABI 表核对通过。

实际入口偏移 `0x2000`，相对写入位置 `0x5ef8`，指针目标偏移 `0x6000`。RELRO 页为
`[0x5000, 0x6000)`，第一个未提交洞为 `0x1000`。两个调用依次得到 `0x448f` 与 `0x4c8d`。

| 载入基址 | 读取到的相对重定位结果 |
| --- | --- |
| `0x100000200000` | `0x100000206000` |
| `0x180040000000` | `0x180040006000` |

RELRO 写、RW 执行和洞读分别在 `0x100000205ef8`、`0x100000206000`、
`0x100000201000` 得到向量 14。RW 执行的 RIP 与故障地址相同。
正常退出和三个故障退出后，空闲页、任务及完成记录均回到 `129711 / 3 / 1`。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `fa9ab7324b44240e` manifest | `ce356ec78ba39744ee936a7c6a6022c9ce20e88bb902b5b386f3e33ec76e13f2` |
| 系统 ISO | `7959f863faecfec73657659ee28ec2b2571c2baad710e24b4ee782ab2478953c` |
| glibc SDK manifest | `bf9e841c1bf27f2330ef2e91a49518ca92fbdfe48d1b7c79a566a49ab9b9caed` |
| glibc SDK 树 | `ab1fc6a1e716b0849109615868ec33b19bec142197950e81c1a873aeea95b0c3` |
| glibc C profile | `ed43f77698a47fbf9c6bd74f90df5c1b27b062d4bbb0a35909fb4c4645958d0e` |
| `layout.so` | `eda19595ee2f31bc92c39ad278a28110b2520642f7f317fe3987cebcae3d6c91` |
| `harness.elf` | `acea8e3a5c33a2432183e6ff4d3b002277bbe2bc8e5d5ab281bdf3e35259a150` |
| `build/d1-exact-evidence/report.json` | `3628b9e3d8e8f21bdcd530cb17f1b8edd5789a024821712e50c6db30e4e0de1d` |
| `build/d1-exact-evidence/d1_layout_serial.log` | `97585193a44e1a7b924f38cea24d138394bee490f5a764db8e93693a9c131571` |

完整 D1 的原生身份、共享依赖和版本、PIE 与 glibc rtld 交接尚未验证。
本轮使用单一固定工件，通用 ELF 动态装载、故障恢复、TLS 与生产准入留在各自验收阶段。
