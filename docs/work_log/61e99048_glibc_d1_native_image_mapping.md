# 61e99048 · D1 原生文件映射组件

基于 `24a9aead`。受测源码与公开提交 `fd4ea75358631863e9dc8204f4a17be502ef3af4`
的 Git 树 `5db46f858c40faf140a0c5321363eaa8c3adf34f` 一致。原来的高地址试验
使用内嵌 PIC 工件，普通 Xsh 装载器用
`elf::inspect_reader` 和低窗构造机制接收静态 `ET_EXEC`。D1 的私有入口栈
已有 `mapped_image` 描述。共享 glibc 的 `dl-sysdep` 仍要求独立原生启动后端。

新的私有映射组件进入普通 SDK 的 `libxos_loader.a`。调用者提供已核验的、有序、
页面不重叠的 LOAD 描述、文件大小、精确高地址偏移和预算，以及来自同一已认证
只读 pin 的读取函数。普通静态装载器与 bootstrap 复用同一份文件读取实现，原生
映射选择定位读，旧静态装载继续按现有规则探测早期文件服务。

映射先核算只保留空间和实际提交页的预算，覆盖至多 64 份 LOAD，扫描的总跨度
限制到原进程 256 MiB 页容量。它以非替换方式精确保留地址，只对 LOAD 提交
RW+NX 零页，按文件偏移复制字节，随后按段落实 R、RX 或 RW 权限。超过单次
sys67 提交或保护上限时分批调用，段间洞一直保持未提交。映射失败撤回整个保留
区；原生撤回错误单独返回，调用方必须终止 bootstrap。成功后由调用方持有映射
并决定释放时机。ELF 身份、文件高阶对齐、重定位、RELRO、解释器启动和 ready
信号均由各自经核验的阶段负责。

## 真实构建与客体

```sh
python3 -B scripts/build.py --output-dir build/d1-native-system
python3 -B tests/glibc_d1_native_image_map_guest.py \
  --system build/d1-native-system --output build/d1-native-map-guest
```

在 macOS arm64 上用实际 GCC 16.2.0 `-fPIC` 和 GNU ld `-shared` 生成普通
`ET_DYN` 文件。它与此前 D1 固定工件的摘要相同。生成的头文件只存 LOAD
描述和摘要。`crt0.o` 无 libc 的静态入口连接候选归档，在 QEMU 11.1.2 从
私有 FAT 盘打开该文件，核对同一只读 pin 的完整 SHA-256 后复制到两个独立
高地址。两处分别验证原始 BSS、做该工件唯一经核对的相对数据修补、调用 sys67
令 RELRO 只读，再调用 RX 段得到 `0x448f` 和 `0x4c8d`。两处的地址分别为
`0x100000200000` 和 `0x180040000000`。文件游标保持 73，pin 显式关闭。

保留预算失败、第一次复制后的模拟短读和精确地址碰撞分别走失败路径。预算拒绝
和短读撤回后，同地址能重新保留；碰撞保留原映像，解映射后两个地址都能重用。
该真实 `ET_DYN` 从 Xsh 普通静态入口被拒绝。静态 bootstrap 正常退出 0，
客体前后均为 129696 空闲页、3 个任务、1 个完成记录。

Linux arm64 上的原定位读取回归以 ASan/UBSan 通过，涵盖旧服务、短读、游标和
原静态装载。私有入口栈用真实目标编译器复编，Linux x86-64 上的原栈回归在 UBSan
下通过三类启动记录、三次栈交接、64+64 参数环境容量和 11 项拒绝检查。公共
ABI 登记的 78 行与源码一致。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `d4a3d8f1a8d0a963` manifest | `09e89113cff8abb8817a742876a0a6ffc916be9d634e0d916b98b9da363467a4` |
| 系统 ISO | `61c36eebb1cd50329eb64de41d03287d1681982365a045c0895e4ea8ac78c392` |
| 正常 SDK loader 归档 | `3cb899e6813ea6a4f4fa5ffdbb3b24bbdb4bd0adb3dc8b5559fe40be57e54ea9` |
| 真实 GCC PIC `layout.so` | `eda19595ee2f31bc92c39ad278a28110b2520642f7f317fe3987cebcae3d6c91` |
| 无 libc 原生 bootstrap ELF | `0dfb3e033efda83394024002968d5710ca91c44fa725e258ca4505370d55c3b7` |
| 客体回执 | `3f818ff2e6deaa77f88a825a6e7e7ff044b5c08586db534d7596e6a9d3f7a24c` |
