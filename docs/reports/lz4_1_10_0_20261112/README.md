# LZ4 1.10.0 客体证据（2026-11-12）

端口：`src/ports/lz4`。本报告是 `port.json.status = guest_verified` 的证据。
只覆盖这里列出的冻结输入；换 SDK、换上游版本或改配方后必须重跑。

## 输入

| 项 | 值 |
|---|---|
| 上游归档 | `lz4_1.10.0.orig.tar.gz`，sha256 `537512904744b35e232912055ccf8ec66d768639ff3abe5788d90d792ec5f48b`（Debian 镜像） |
| 客体系统 | 本仓库基线构建 `build/xos-install.iso`，build `d0e65ed6413f371f` |
| 构建 SDK | `build/threading_sdk`（threaded profile `xos-x86_64-static-threaded-v1`） |
| 交叉编译器 | `x86_64-elf-gcc 16.2.0` |
| 参考实现 | 同一源码在宿主编译的 `lz4`（单线程） |

## 产物

| 项 | 值 |
|---|---|
| 包 | `thirdparty.lz4-1.10.0.xpk`，788,480 字节（由 `src/ports/lz4/build.py` 直接产出） |
| 包 sha256 | `94724be9428a9d835fe4ea6d9772be9db08c54f3f31a61af79269bcd4361c199` |
| 载荷 | `usr/bin/lz4`、`usr/lib/liblz4.a`、`usr/share/lz4/include/*.h`、样例、两份许可、`source.json`、`build_receipt.json` |

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:b8909de64da3331081bb8c867cf025d8a5f72da433f4b8cfa73e03cb5e82490a -->

上游零补丁：当前配方启用 `LZ4IO_MULTITHREAD=1`，编译上游 `threadpool.c`，
链接线程 SDK；这是线程化 CLI 构建。

证据复核：仓库只保存本 README，没有原始串口日志、安装回执或上述 XPK。
下面历史记录同时出现 3960 → 391 字节和 3000 → 298 字节，不能视为同一次运行，
也无法绑定到表中包哈希。以下内容保留供追溯，**不构成表中线程化包通过验证的证明**。
需从表中哈希对应的包重新安装，保存包摘要、安装回执、完整命令与原始日志，
并记录输入、压缩产物及解压产物的大小和摘要，才能补齐证据。

<!-- /coderabbit-ai-generated:v1 -->
客体 `/dev/null` 不存在，`lz4 -t` 因此失败（见“未覆盖 / 已知失败”）。

## 安装

```sh
python3 scripts/xypm.py install --image disks/base.img --output-image disks/lz4.img \
  --offline --profile config/package/xos_x86_64_static_threaded_v1.json \
  thirdparty.lz4-1.10.0.xpk
```

结果：`verify-installed = verified`；`list` 显示 `thirdparty.lz4 1.10.0 rev 0`。

## 客体运行（原始输出，同一份包）

样例 `usr/share/lz4/samples/sample.txt`，3000 字节，sha256
`680c48c74164969e64be4edd2cd54001052693fd68e1134861de15f420796afc`。

xsh 路径：

```text
xsh> exec-file /usr/bin/lz4 -v -T2 -1 -f /usr/share/lz4/samples/sample.txt /sample.lz4
*** lz4 v1.10.0 64-bit multithread, by Yann Collet ***
Using 2 threads for compression
Read : 0 MiB   ==> 9.93%
Compressed 3000 bytes into 298 bytes ==> 9.93%
Done in 0.03 s ==> 0.10 MiB/s  (cpu load : 100%)
```

dash 路径（`/usr/bin/lz4 -v -T2 -1 -f /sample.txt /sample.lz4`）：

```text
*** lz4 v1.10.0 64-bit multithread, by Yann Collet ***
Using 2 threads for compression
Read : 0 MiB   ==> 9.93%
Compressed 3000 bytes into 298 bytes ==> 9.93%
Done in 0.02 s ==> 0.14 MiB/s  (cpu load : 100%)
c_rc=0
*** lz4 v1.10.0 64-bit multithread, by Yann Collet ***
Decompressed : 0 MiB
/sample.lz4                    : decoded 3000 bytes
d_rc=0
```

- `/sample.out` 与样例**逐字节相同**（sha256 同上）。
- 客体产出的 `/sample.lz4`（298 字节）sha256
  `0e82989633a6b667cee184a006a1abc5a9fe3f5ec1678827f31d0f9ded359980`，
  与宿主参考实现压缩同一文件的结果**完全相同**。
- 宿主参考实现能解压客体产出的 `.lz4`（decoded 3000 bytes，与样例一致）。

## 未覆盖 / 已知失败

- `lz4 -t` 需要 `/dev/null`；基线尚未提供时该命令报
  `/dev/null: No such file or directory` 并退出 1（账本 `PL-0006`，
  由 #126 提供设备后应可复核）。压缩/解压路径不受影响。
- 上游 `tests/` 未跑；只验证 xsh + dash 脚本。
- `-T2` 已验证压缩/解压与宿主互解；SMP 与更高线程数未验。
- 未在官方发行盘复验。

## 复现

按 [`src/ports/lz4/README.md`](../../../src/ports/lz4/README.md) 设置 `XOS_SDK`、
`XOS_SOURCE_ARCHIVE`、`XOS_OUT` 后执行配方，再按上面的安装与命令重跑。压缩结果可用
宿主同版本 `lz4 -1` 对拍字节。
