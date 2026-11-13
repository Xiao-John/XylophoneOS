# bc/dc 1.08.2 客体证据（2026-11-12）

| 项 | 值 |
|---|---|
| 端口 | `src/ports/bc` |
| 上游归档 | `bc-1.08.2.tar.gz`，sha256 `ae470fec429775653e042015edc928d07c8c3b2fc59765172a330d3d87785f86`（aliyun GNU 镜像） |
| 构建方式 | autotools 交叉 configure（`--without-readline --disable-nls`）+ `make -C lib/bc/dc` |
| 构建 SDK | 仓库开发树 `build/sdk`，build `26161cda4ebf8109` |
| 包 | `thirdparty.bc-1.08.2.xpk`，sha256 `0238071e5929e03435da4251b5fae0773701754828f3f576c78016d12d26e166` |
| 目标 profile | `xos-x86_64-static-single-b2-v1` |

## 安装事务

```text
python3 scripts/xypm.py install --image base.img --output-image work.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json thirdparty.bc-1.08.2.xpk
-> backend_sha256 e91e45adc5b6df7adc3dfb761a411debd2aeccac4684c2b5d4464fc3519c92b6
```

## xsh 原始输出

```text
xsh> exec-file /usr/bin/bc -l -q /usr/share/bc/samples/calc.bc
3.14159265358979323844
1.41421356237309504880
1267650600228229401496703205376
FF
DEADBEEF
xsh> exec-file /usr/bin/dc /usr/share/bc/samples/calc.dc
32
FF
```

`calc.bc` 内容：`scale=20; pi=4*a(1); pi; sqrt(2); 2^100; obase=16; 255;
ibase=16; DEADBEEF; quit`。

## dash 原始输出

```text
$ /usr/bin/bc -l -q /usr/share/bc/samples/calc.bc
3.14159265358979323844
1.41421356237309504880
1267650600228229401496703205376
FF
DEADBEEF
bc_rc=0
$ echo '2+3*4' | /usr/bin/bc -q
14
pipe_rc=0
$ echo '1 2 + p' | /usr/bin/dc
3
dc_rc=0
$ /usr/bin/bc --version
bc 1.08.2
```

## 未覆盖

- 交互式 REPL（终端行编辑，readline 已关闭）未做自动化验证。
- `xsh exec-file` 下 bc 读 stdin 出现 `read() in flex scanner failed`（样例用 `quit`
  收尾规避）；管道与脚本输入正常。

## 根因：控制台读取是非阻塞的

最小探针（`read(0, buf, 32)`，经 `exec-file` 在 xsh 下运行）：

```text
xsh> exec-file /rdprobe
read=-1 errno=11
```

链路：

1. `src/kernel/arch/x86_64/tasks.cpp:1184` `stdio_read(..., console_empty_is_error)`：
   控制台无字节时返回 `process_error_would_block`（`sys_handle_read` 传 `true`），
   旧 `sys_read` 传 `false` 时返回 0（*EOF*）。
2. 内核没有“控制台可读”等待原语：`sys_pipe_wait` 只对 pipe 有效
   （`pipe_read_from`/`wake_pipe_waiters`），控制台读取无法阻塞。
3. `src/user/libc/newlib_syscalls.cpp:681` `read()` 对 kernel/pipe 句柄循环
   `read + sys_pipe_wait`；控制台句柄的 `pipe_wait` 失败，于是把 `would_block`
   映射成 `EAGAIN`（注释明确写着“保留原来的非阻塞控制台行为”）。
4. `bc` 的 flex 扫描器把 `read()` 的负返回值当成致命错误，打印
   `read() in flex scanner failed` 并以 2 退出。

xsh 自身不受影响，是因为它用 `debug_peek`/轮询读取；pipe 与脚本输入走
`sys_pipe_wait`，能正常阻塞/EOF。
- 上游 `Test/` 套件未跑。
