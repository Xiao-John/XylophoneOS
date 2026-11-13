# zlib 1.3.1 客体证据（2026-11-13）

| 项 | 值 |
|---|---|
| 端口 | `src/ports/zlib` |
| 上游归档 | `zlib-1.3.1.tar.gz`，sha256 `9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23`（zlib.net fossils） |
| 构建方式 | `./configure --static` + `make libz.a` + 手工链接 `test/minigzip.c` |
| 构建 SDK | 仓库开发树 `build/sdk` |
| 包 | `thirdparty.zlib-1.3.1.xpk`，sha256 `21520a68ee52aa397d0bfc93a4c3b3e4274626f8d2b0b8dab978dbd3f5e4c6d9`，8 个文件 |
| 目标 profile | `xos-x86_64-static-single-b2-v1` |

## 安装事务

```text
python3 scripts/xypm.py install --image base.img --output-image work.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json thirdparty.zlib-1.3.1.xpk
-> verified_files 8, mutations 22, backend_sha256 0d8023a3…
```

## xsh 原始输出

```text
xsh> exec-file /usr/bin/minigzip -d -c /s.gz
ZLIB DATA COMPRESSION LIBRARY
...
zlib 1.3.1 is a general purpose data compression library. ...
```

## dash 原始输出

`dash /tests/zl2.sh`（bare command，dash 有 spawn 权限）：

```text
/tests/minigzip -c /usr/share/zlib/samples/sample.txt > /s.gz
c_rc=0
/tests/minigzip -d -c /s.gz > /s.out
d_rc=0
```

## 互操作

- 客体 `/s.gz` 2527 字节，头 `1f 8b 08`；宿主 `gzip -d` 解压成功。
- 宿主解压结果与客体 `/s.out`（5317 字节）逐字节相同。

## 未覆盖

- `minigzip` 是示例 CLI：无 `-t/-l/-r`，未做递归/后缀批量处理。
- 上游 `make test` 未跑。
- GNU gzip CLI 需要 gnulib OS 后端，另议。
- `exec-file` 启动的 dash 无 spawn 权限，脚本必须用 bare `dash` 运行。
