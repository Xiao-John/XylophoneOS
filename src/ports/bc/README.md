# GNU bc / dc 1.08.2（XOS 端口）

GNU 的任意精度计算器 `bc` 与逆波兰计算器 `dc`，同一份上游源码。

## 状态

`guest_verified`（2026-11-12）。上游零补丁；`--without-readline --disable-nls`。

- 包 id：`thirdparty.bc`
- 目标 profile：`xos-x86_64-static-single-b2-v1`
- 已验证包哈希：`0238071e5929e03435da4251b5fae0773701754828f3f576c78016d12d26e166`
  （由本目录配方构建；换 SDK/上游/配方后必须重算并更新 `port.json`）。

## 构建

```sh
export XOS_SDK=/path/to/xos_sdk
export XOS_SOURCE_ARCHIVE=/path/to/bc-1.08.2.tar.gz
export XOS_OUT=/path/to/out
python3 build.py
```

配方用 autotools 交叉构建：`./configure --host=x86_64-elf --without-readline
--disable-nls`，然后分别 `make -C lib`、`make -C bc`、`make -C dc`（顶层 `all`
会尝试生成 Info 文档，宿主缺少 `makeinfo` 时失败，因此不走 `all`）。

## 安装与验证

```sh
python3 scripts/xypm.py install --image base.img --output-image work.img --offline \
  --profile config/package/xos_x86_64_static_single_b2_v1.json thirdparty.bc-1.08.2.xpk
```

客体（xsh 直接调用，或用 `dash` 脚本）：

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

`dash` 同一份包：

```text
$ bc -l -q /usr/share/bc/samples/calc.bc   -> bc_rc=0
$ echo '2+3*4' | bc -q                      -> 14
$ echo '1 2 + p' | dc                       -> 3（dc_rc=0）
$ bc --version                              -> bc 1.08.2
```

## 已知限制

- 交互式 `bc` 在 xsh 的 `exec-file` 下读 stdin 时可能报 `read() in flex scanner failed`
  并以 2 退出。根因是 OS 侧控制台读取语义：空输入返回 `EAGAIN`（非阻塞），
  POSIX 程序按 `read()` 失败处理。详见证据报告“根因”一节；样例以 `quit` 收尾，
  或改用管道/`dash` 输入。
- 未安装 man/info 文档；`bc -l` 的数学库来自上游 `lib/libmath.h`，已随构建内置。
- 上游 `Test/` 套件未跑。
