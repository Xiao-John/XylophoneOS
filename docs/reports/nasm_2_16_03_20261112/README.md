# NASM 2.16.03 客体证据（2026-11-12）

端口：`src/ports/nasm`。本报告是 `port.json.status = guest_verified` 的证据。
只覆盖这里列出的冻结输入；换 SDK、换上游版本或改配方后必须重跑。

## 输入

| 项 | 值 |
|---|---|
| 上游归档 | `nasm-2.16.03.tar.xz`，sha256 `1412a1c760bbd05db026b6c0d1657affd6631cd0a63cddb6f73cc6d4aa616148`（BLFS 镜像，未与 nasm.us 二次比对） |
| SDK | `xylophoneos_revival_0.0.2-1103_sdk`，`manifest.json.build_id = 8356e45af316fc93` |
| 交叉编译器 | `x86_64-elf-gcc 16.2.0` |
| 客体系统 | 本仓库 main 构建的 `build/xos-install.iso`，build `0d9e4e844e51f7b5`（kernel 713560 字节） |
| QEMU | 11.1.2，`qemu64,+rdrand`，TCG |

未使用官方 0.0.2-1103 发行盘：本地那份 `..._1103_images.tar.gz` 已损坏
（`gzip: data stream error`，`work_disk.img` 截断），无法复验。

## 产物

| 项 | 值 |
|---|---|
| 包 | `thirdparty.nasm-2.16.03.xpk`，1,730,560 字节（由 `src/ports/nasm/build.py` 直接产出） |
| 包 sha256 | `0b7940222df8c08fe76ccb289b7117b35fd7690afe52cbf05825416a54a88d11` |
| 载荷 | `usr/bin/nasm`、`usr/share/licenses/thirdparty.nasm/LICENSE`、`usr/share/nasm/{source.json,build_receipt.json,hello.asm,macro64.asm}` |
| `usr/bin/nasm` | 1,716,416 字节，ELF64 `EXEC`，入口 `0x40000000`，无 `INTERP`，3 段 LOAD + TLS |
| 宿主校验 | `xypm.py verify` = `verified_integrity_only` / `profile_checked` |

上游 1190 个源文件与干净的 `nasm-2.16.03.tar.xz` 逐字节一致（逐文件 sha256 比对，
差异 0）：**没有源码补丁**。构建只使用 `configure` 的交叉探测结果（`HAVE_MMAP`、
`HAVE_REALPATH` 未定义，走 NASM 自带实现）和 SDK 链接参数。

## 安装

```sh
python3 scripts/xypm.py install \
  --image disks/base.img --output-image disks/run5.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json \
  thirdparty.nasm-2.16.03.xpk
```

结果：`verified_files: 6`；`verify-installed` 返回 `{"status": "verified", "files": 6}`；
`list` 显示 `thirdparty.nasm 2.16.03 rev 0`。卸载事务也验证过：`remove` 后 `list` 为空。

## 客体运行（xsh，原始输出）

```text
xsh> exec-file /usr/bin/nasm -v
NASM version 2.16.03 compiled on Nov 12 2026
xsh> exec-file /usr/bin/nasm -f bin /usr/share/nasm/hello.asm -o /hello.bin
xsh> exec-file /usr/bin/nasm -f elf64 /usr/share/nasm/macro64.asm -o /macro64.o
xsh> exec-file /usr/bin/nasm /nonexistent.asm -o /x.bin
nasm: fatal: unable to open input file `/nonexistent.asm' No such file or directory
xsh: program exited with status 1
xsh> exec-file /usr/bin/nasm -h
（打印完整选项与 --limit-X 列表）
```

关闭 QEMU 后从工作盘导出产物核对：

| 文件 | 结果 |
|---|---|
| `/hello.bin` | 6 字节 `b8 34 12 cd 10 f4`（sha256 `b34a05a19ebb47d6d059488b8c9ceb350970e944c484e0df59423f5fc284ba97`） |
| `/macro64.o` | 592 字节，ELF64 `REL`，含全局 `_start`；反汇编 `b8 3c 00 00 00 / bf 00 00 00 00 / 0f 05 / 90 90`（sha256 `4b00a318c7fc2c1771accb68ff6b6a530ddd0584550dd8d707c094ef7c5cf1ef`） |

`hello.asm` 与 `macro64.asm` 是包内自带的样例（`src/ports/nasm/samples/`），因此这条
验收不依赖仓库外的源文件。

## 未覆盖

- NASM 自带 `test/` 套件未跑；`ndisasm` 未构建。
- 只测 xsh；dash 未测。
- 未在官方 0.0.2-1103 发行盘上复验（原因见上）。
- 未比较 `nasm.us` 官方归档哈希。

## 复现

按 [`src/ports/nasm/README.md`](../../../src/ports/nasm/README.md) 设置
`XOS_SDK`、`XOS_SOURCE_ARCHIVE`、`XOS_OUT` 后执行配方，再按上面的 `xypm.py install`
与 `exec-file` 命令重跑。客体输出用 `scripts/work_disk.py export` 导出核对。
