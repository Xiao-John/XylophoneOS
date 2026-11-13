# xxHash 0.8.3 客体证据（2026-11-12）

端口：`src/ports/xxhash`。本报告是 `port.json.status = guest_verified` 的证据。
只覆盖这里列出的冻结输入；换 SDK、换上游版本或改配方后必须重跑。

## 输入

| 项 | 值 |
|---|---|
| 上游归档 | `xxhash_0.8.3.orig.tar.gz`，sha256 `aae608dfe8213dfd05d909a57718ef82f30722c392344583d3f39050c7f29a80`（Debian 镜像的 orig tarball，未与 GitHub release 附件比对） |
| SDK | `xylophoneos_revival_0.0.2-1103_sdk`，`manifest.json.build_id = 8356e45af316fc93` |
| 交叉编译器 | `x86_64-elf-gcc 16.2.0` |
| 客体系统 | 本仓库 main 构建的 `build/xos-install.iso`，build `0d9e4e844e51f7b5` |
| 参考实现 | 同一份源码用宿主 clang 编译的 `xxhsum 0.8.3`（用于对拍哈希值） |

未使用官方 0.0.2-1103 发行盘：本地那份 `..._1103_images.tar.gz` 已损坏
（`gzip: data stream error`，`work_disk.img` 截断）。

## 产物

| 项 | 值 |
|---|---|
| 包 | `thirdparty.xxhash-0.8.3.xpk`，532,480 字节（由 `src/ports/xxhash/build.py` 直接产出） |
| 包 sha256 | `cbd24a96cfc6cfa26071b7286ad84431b47475230d60d8764d3b6ba536875495` |
| 载荷 | `usr/bin/xxhsum`（188,256 B）、`usr/lib/libxxhash.a`（38,888 B）、`usr/share/xxhash/include/xxhash.h`、`usr/share/xxhash/samples/hello.txt`、两份许可文本、`source.json`、`build_receipt.json` |
| 库导出 | `XXH32`、`XXH64`、`XXH3_64bits` 等（`nm --defined-only libxxhash.a`） |
| 宿主校验 | `xypm.py verify` = `verified_integrity_only` / `profile_checked` |

上游源码未打补丁：配方直接编译归档里的 `xxhash.c` 与 `cli/*`，只额外编译端口侧
`compat/times.c`（newlib `clock()` 需要 `times()`，SDK 只导出 `_times()`）。

## 安装

```sh
python3 scripts/xypm.py install \
  --image disks/base.img --output-image disks/xxhash.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json \
  thirdparty.xxhash-0.8.3.xpk
```

结果：`verify-installed = verified`；`list` 显示 `thirdparty.xxhash 0.8.3 rev 0`。

## 客体运行（dash 脚本，原始输出）

样例文件 `usr/share/xxhash/samples/hello.txt`（内容 `hello xxhash\n`，
sha256 `da7b09d4c0f7cfee2b90a02631345a6b3e5b0950d9c212c273509311c18113e3`）。

```text
xxhsum 0.8.3 by Yann Collet
compiled as 64-bit x86_64 + SSE2 little endian with GCC 16.2.0
104754c5  /usr/share/xxhash/samples/hello.txt
1fcb86cd080a6d68  /usr/share/xxhash/samples/hello.txt
62ee07f5a88eb706798eef4b08d9d85f  /usr/share/xxhash/samples/hello.txt
XXH3_1e3102046b859e0f  /usr/share/xxhash/samples/hello.txt
1fcb86cd080a6d68  stdin
/usr/share/xxhash/samples/hello.txt: OK
check_rc=0
Error: Could not open '/missing': No such file or directory.
missing_rc=1
```

对应算法：`-H0`=XXH32、`-H1`=XXH64、`-H2`=XXH128、`-H3`=XXH3-64。

宿主参考实现对同一文件给出完全相同的结果：

```text
104754c5  ...
1fcb86cd080a6d68  ...
62ee07f5a88eb706798eef4b08d9d85f  ...
XXH3_1e3102046b859e0f  ...
1fcb86cd080a6d68  stdin
```

## 未覆盖

- 上游 `tests/`（`make check`）未跑。
- 未在客体里编译链接 `libxxhash.a`（客体无编译器）；仅在宿主用 `nm` 核对导出符号。
- 只验证 xsh 与 dash 脚本；dash 的 `-c` 单引号参数受 xsh 传参切分限制，未使用。
- 未在官方 0.0.2-1103 发行盘复验（镜像包损坏）。
- 未与 GitHub release 附件的哈希二次比对。

## 复现

按 [`src/ports/xxhash/README.md`](../../../src/ports/xxhash/README.md) 设置
`XOS_SDK`、`XOS_SOURCE_ARCHIVE`、`XOS_OUT` 后执行配方，再按上面的 `xypm.py install`
与命令重跑；哈希对拍可用宿主编译的同版本 `xxhsum`。
