# Lua 5.4.9 客体证据（2026-11-12）

端口：`src/ports/lua`。本报告是 `port.json.status = guest_verified` 的证据。
只覆盖这里列出的冻结输入；换 SDK、换上游版本或改配方后必须重跑。

## 输入

| 项 | 值 |
|---|---|
| 上游归档 | `lua5.4_5.4.9.orig.tar.gz`，sha256 `2335b6c582a52654f94612bf10d2f4672805d05329aa6568b1d8cd9e5c6fb8e6`（Debian 镜像） |
| 客体系统 | 本仓库基线构建 `build/xos-install.iso`，build `70ad88bf4d90e9cd`，kernel 721752 字节 |
| 交叉编译器 | `x86_64-elf-gcc 16.2.0` |

## 产物

| 项 | 值 |
|---|---|
| 包 | `thirdparty.lua-5.4.9.xpk`，1,044,480 字节（由 `src/ports/lua/build.py` 直接产出） |
| 包 sha256 | `49f80fd37adad0783ba99d0aa20eedc678a4735619300af50979cd6342b84fb2` |
| 载荷 | `usr/bin/lua`、`usr/lib/liblua.a`、`usr/share/lua/include/{lua,luaconf,lauxlib,lualib}.h`、样例、许可（`doc/readme.html`）、`source.json`、`build_receipt.json` |

上游零补丁、无端口 shim；默认 C99 配置（不启用 `LUA_USE_POSIX`，因此没有
readline/popen 依赖）。

## 安装

```sh
python3 scripts/xypm.py install --image disks/base.img --output-image disks/lua.img \
  --offline --profile config/package/xos_x86_64_static_single_b2_v1.json \
  thirdparty.lua-5.4.9.xpk
```

结果：`verify-installed = verified`；`list` 显示 `thirdparty.lua 5.4.9 rev 0`。

## 客体运行：xsh 路径（原始输出）

```text
xsh> exec-file /usr/bin/lua -v
Lua 5.4.9  Copyright (C) 1994-2026 Lua.org, PUC-Rio
xsh> exec-file /usr/bin/lua /usr/share/lua/samples/hello.lua
Lua 5.4
fib(10)=55
squares=1,4,9,16,25
fmt=xos/42/3.50
xsh> exec-file /usr/bin/lua /missing.lua
/usr/bin/lua: cannot open /missing.lua: No such file or directory
xsh: program exited with status 1
```

## 客体运行：dash 路径（原始输出）

`/tests/lua.sh`：

```sh
/usr/bin/lua -v
/usr/bin/lua /usr/share/lua/samples/hello.lua
/usr/bin/lua -e 'print("expr=" .. tostring(2^10))'
echo dash_rc=$?
```

```text
Lua 5.4.9  Copyright (C) 1994-2026 Lua.org, PUC-Rio
Lua 5.4
fib(10)=55
squares=1,4,9,16,25
fmt=xos/42/3.50
expr=1024.0
dash_rc=0
```

两条路径对同一脚本输出一致；`-e` 只在 dash 脚本里测（xsh 不做 shell 引号处理）。

## 未覆盖 / 已知失败

- `os.execute`/`io.popen` 不可用：`system()`/`popen()` 只有 ENOSYS 桩，实测
  `os.execute("true")` 返回 `nil, "Function not implemented", 88`。记入
  [端口反馈账本](../../ports_ledger.md) `PL-0007`，属大项，攒批开 issue。
- 未构建 `luac`；未跑上游 `tests/`；未在官方发行盘复验。

## 复现

按 [`src/ports/lua/README.md`](../../../src/ports/lua/README.md) 设置 `XOS_SDK`、
`XOS_SOURCE_ARCHIVE`、`XOS_OUT` 后执行配方，再按上面的安装与两条路径重跑。
