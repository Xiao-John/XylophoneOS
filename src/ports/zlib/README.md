# zlib 1.3.1（XOS 端口）

zlib 压缩库与 `minigzip`（gzip 格式的压缩/解压示例工具）。

## 状态

`guest_verified`（2026-11-13）。上游零补丁。

- 包 id：`thirdparty.zlib`
- 目标 profile：`xos-x86_64-static-single-b2-v1`
- 已验证包哈希：`aa795f283785252aa68e84c8b6eba3eb0e3ea7cb22b43310b8408f241ad72fd8`
  （由本目录配方构建；换 SDK/上游/配方后必须重算并更新 `port.json`）。

## 构建

```sh
export XOS_SDK=/path/to/xos_sdk
export XOS_SOURCE_ARCHIVE=/path/to/zlib-1.3.1.tar.gz
export XOS_OUT=/path/to/out
python3 build.py
```

配方会核对 `XOS_SDK` 树哈希是否登记在目标 profile 的 `sdk_tree_sha256`；用开发树
`build/sdk`（未登记）构建时需设置 `XOS_SDK_UNREGISTERED_OK=1`。

配方：`./configure --static` → `make libz.a`，再用 SDK 的 crt0/链接脚本编译
`test/minigzip.c`。安装 `/usr/bin/minigzip`、`/usr/lib/libz.a`、
`/usr/share/zlib/include/{zlib.h,zconf.h}`。

## 安装与验证

```sh
python3 scripts/xypm.py install --image base.img --output-image work.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json thirdparty.zlib-1.3.1.xpk
```

客体（xsh 直接调用，或用 `dash` 脚本）：

```text
xsh> exec-file /usr/bin/minigzip -d -c /s.gz
ZLIB DATA COMPRESSION LIBRARY
...
```

```text
$ dash /tests/zl2.sh
/usr/bin/minigzip -c samples/sample.txt > /s.gz  -> c_rc=0
/usr/bin/minigzip -d -c /s.gz > /s.out           -> d_rc=0
```

产物 `/s.gz`（2527 字节，`1f 8b 08` 头）可被宿主 `gzip -d` 解开，解压结果与
`/s.out` 逐字节相同。

## 已知限制

- `minigzip` 是 zlib 的示例 CLI，不是 GNU gzip：没有 `-t/-l/-r` 等完整选项面，
  也不做 `.gz` 后缀的批量处理。
- 为什么没有直接移植 GNU gzip：gzip 1.14 依赖 gnulib，而 gnulib 目前没有 XOS
  后端（`getprogname.c` 直接 `#error "not ported to this OS"`，`getdtablesize`
  还要求 rlimit 等）。这是长期项，见 issue 讨论；zlib 先把 `.gz` 读写能力落地。
- 通过 `exec-file` 启动的 `dash` 没有 spawn 权限，无法再执行子进程（会报
  `No such file or directory`）；请用 bare command（`dash script`）运行脚本。
