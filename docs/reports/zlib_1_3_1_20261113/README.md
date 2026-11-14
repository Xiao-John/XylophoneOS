# zlib 1.3.1 客体证据（2026-11-13）

| 项 | 值 |
|---|---|
| 端口 | `src/ports/zlib` |
| 上游归档 | `zlib-1.3.1.tar.gz`，sha256 `9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23`（zlib.net fossils） |
| 构建方式 | `./configure --static` + `make libz.a` + 手工链接 `test/minigzip.c` |
| 目标 profile | `xos-x86_64-static-single-b2-v1` |
| 客体系统 | `build/xos-install.iso`，build `41f3fce8bbf46593`，kernel 805016 字节 |
| 构建 SDK | 开发树 `build/sdk`；SDK build `41f3fce8bbf46593`；树哈希 `78fe9a04248bea82d79ff10bcecfb4036dc94d590d24109bdfc5ed94e33ea18c`（未登记到 profile，构建时使用 `XOS_SDK_UNREGISTERED_OK=1`） |
| 包 | `thirdparty.zlib-1.3.1.xpk`，sha256 `3f00b879fc9db9986eb0208c08c2e18a7053f4da19122ff9bd8c2206593b4581`，8 个文件 |
| `minigzip` 交付物 | `usr/bin/minigzip`，sha256 `271647853907888bf8925c2409b8ebe169045df90879586172c65ab035c763d3`，216576 字节 |

## 安装事务

```text
python3 scripts/xypm.py install --image base.img --output-image work.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json thirdparty.zlib-1.3.1.xpk
-> verified_files 8, mutations 22, backend_sha256 0d8023a31e1aefee2e484e0e14b1db939aaac9ae4757ab40a41690a19756e7e7
```

安装后导出 `/usr/bin/minigzip` 复核摘要为
`271647853907888bf8925c2409b8ebe169045df90879586172c65ab035c763d3`，与 XPK 内
`payload/usr/bin/minigzip` **完全一致**；两个 shell 都直接运行这个已安装路径，
不再使用 `/tests/minigzip` 副本。

## xsh 原始输出

```text
xsh> exec-file /usr/bin/minigzip -d -c /s.gz
ZLIB DATA COMPRESSION LIBRARY

zlib 1.3.1 is a general purpose data compression library.  All the code is
thread safe.  The data format used by the zlib library is described by RFCs
...
```

## dash 原始输出

`dash /tests/zl2.sh`（bare command，dash 有 spawn 权限）：

```text
/usr/bin/minigzip -c /usr/share/zlib/samples/sample.txt > /s.gz
c_rc=0
/usr/bin/minigzip -d -c /s.gz > /s.out
d_rc=0
```

## 互操作

- 客体 `/s.gz` 2527 字节（头 `1f 8b 08`），sha256 由宿主 `gzip -d` 成功解压。
- 宿主解压结果与客体 `/s.out`（5317 字节，
  sha256 `d106dcdb2a0b3087cb3a2380b9f00a0bbadc7eb835cd80408f94a2d78d69727d`）
  逐字节相同。

## 未覆盖

- `minigzip` 是示例 CLI：无 `-t/-l/-r`，未做递归/后缀批量处理。
- 上游 `make test` 未跑。
- GNU gzip CLI 需要 gnulib OS 后端，另议。
- `exec-file` 启动的 dash 无 spawn 权限，脚本必须用 bare `dash` 运行。
