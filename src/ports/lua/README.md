# lua（上游 Lua 5.4.9）

把 Lua 作为纯客体包交付：解释器 `lua`、静态库 `liblua.a` 与四个公共头文件。
不进内核、不进启动镜像清单，不需要任何 OS 源码改动。

## 状态

`guest_verified`（2026-11-12）。上游零补丁，默认 C99 配置；**xsh 与 dash 两条路径
都实测**。证据见
[docs/reports/lua_5_4_9_20261112](../../../docs/reports/lua_5_4_9_20261112/README.md)。

状态词与升级条件见[端口规范](../../../docs/ports.md)。

## 构建

配方 `build.py` 离线执行，只接受本地归档与冻结 SDK：

```sh
export XOS_SDK=/path/to/xos_sdk
export XOS_SOURCE_ARCHIVE=/path/to/lua5.4_5.4.9.orig.tar.gz
export XOS_OUT=/path/to/empty-output-dir
python3 src/ports/lua/build.py
```

产出 `$XOS_OUT/thirdparty.lua-5.4.9.xpk` 与 `$XOS_OUT/build_receipt.json`。配方编译
`src/*.c`（除 `luac.c`）为 `liblua.a`，再与 `lua.c` 链接成解释器；链接
`user.ld` + `crt0_posix.o` + `libxos/libc/libm/libgcc`。

## 安装与验证

```sh
python3 scripts/xypm.py install \
  --image work_disk.img --output-image with_lua.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json \
  "$XOS_OUT/thirdparty.lua-5.4.9.xpk"
```

已验证的包哈希：`49f80fd37adad0783ba99d0aa20eedc678a4735619300af50979cd6342b84fb2`
（1,044,480 字节，由本目录配方构建；换 SDK、上游或配方后必须重算并更新 `port.json`）。

**xsh**（直接执行）：

```text
exec-file /usr/bin/lua -v
    Lua 5.4.9  Copyright (C) 1994-2026 Lua.org, PUC-Rio
exec-file /usr/bin/lua /usr/share/lua/samples/hello.lua
    Lua 5.4
    fib(10)=55
    squares=1,4,9,16,25
    fmt=xos/42/3.50
```

**dash**（脚本 `/tests/lua.sh`，含 `-e` 与退出码）：

```text
/usr/bin/lua -v
/usr/bin/lua /usr/share/lua/samples/hello.lua
/usr/bin/lua -e 'print("expr=" .. tostring(2^10))'
    expr=1024.0
    dash_rc=0
```

错误路径（xsh）：`exec-file /usr/bin/lua /missing.lua` →
`/usr/bin/lua: cannot open /missing.lua: No such file or directory`，退出 1。

## 已知限制

- `os.execute` 返回 `nil, "Function not implemented", 88`：`system()` 与 `popen()` 只有
  newlib 的 ENOSYS 桩，属账本 `PL-0007`（与 `/dev/null` 等一批开 issue）。
- 未构建 `luac`（编译器），只交付解释器与库。
- 未跑上游 `tests/`。
- 头文件放在 `/usr/share/lua/include/`（xypm 只允许 `/usr/bin`、`/usr/lib`、`/usr/share`）。
- 源码哈希来自 Debian 镜像的 `orig.tar.gz`，未与 lua.org 官方附件二次比对。
- 客体证据绑定当前基线构建与 SDK；换构建输入后需重验。
