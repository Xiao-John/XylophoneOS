# 0038：CPython PY1 脚本与 import

2026-10-25。用户确认 PY0 完成并要求开始 PY1。本组只新增确定性安装 stage、PY1
fixtures/客体测试及 CPython 文档；只读复用 0030 的解释器、标准库、冻结 SDK 和
当前系统镜像。没有修改或重建内核、文件 ABI、files、loader、libc、dash/sbase，
没有清理共享 `build/`，也没有操作日常工作盘。

## 结果

PY1 通过，客体报告 `build/cpython_py1_report.json` 为 6/6：

1. `python3 /work/py1/main.py alpha beta` 得到精确 `sys.argv`，cwd 为 `/`，继承
   `PATH=/usr/bin:/bin:/`，`sys.path[0]` 为 `/work/py1`；同目录 `helper.py` 可导入，
   搜索路径不含 `/Users/` 或 `.cache/xos_seed`。
2. 对 `json`、`re`、`collections`、`itertools`、`functools`、`math` 分别执行了
   JSON/Unicode解析、正则匹配、Counter、accumulate、reduce 和 sqrt；不是只验
   `import`，也不由此声称这些模块的全部 API 或全标准库可用。
3. 工作盘文件 `00 58 0a 7f ff` 在客体二进制读取后仍为相同 5 字节。
4. 不存在的模块产生 `ModuleNotFoundError` 并退出 1。
5. 非法源码产生 `SyntaxError` 并退出 1。
6. 未捕获 `RuntimeError` 打印 traceback 并退出 1。

六次解释器进程退出后均有 `event=reclaimed`，随后回到 `xsh>`；本轮是定向功能
gate，不替代压力测试。

## 可复现安装布局

`scripts/stage_cpython.py` 只接受 `build/cpython_py0b_report.json` 标记为 passed 的
fingerprint，不从“最新 cache”猜构建。0030 的 fingerprint 为
`ad85d8438b4101d66483`，冻结 SDK build 为 `2c3876e640840ff5`。stage 位于：

```text
.cache/xos_seed/cpython/ad85d8438b4101d66483/stage_py1/
  usr/bin/python3
  usr/lib/python3.14/...
  usr/share/licenses/cpython/LICENSE
```

stage 共 560 个文件；`stage_py1_manifest.json` 对每个安装路径记录大小和 SHA256，
自身 SHA256 为
`f76130f7b9e3686011032d07f22a9a307da86f03634e51cbbd371f4a89a7d0b1`。标准库仍排除
`test/`、`idlelib/`、`tkinter/`、`turtledemo/`、`ensurepip/`、`lib2to3/`、
`site-packages/` 和 `__pycache__/`。已有完整 stage 不重写；只出现 stage 或清单之一
时直接报错，避免悄悄覆盖半成品。

测试使用新建的 2 GiB 临时 FAT32 工作盘。系统镜像 build 为
`3d7665a665df9443`，`build/xos.img` SHA256 为
`74b07888492ed1c4c7b2117fcb42568d77a5523715df5375af7e86bfb7842b12`；PY1 报告
SHA256 为 `948aa2627000e404f6f1318315b7d5d455412a0bb81859c38f4231c7733206a5`。

## 实际命令

```sh
/usr/bin/python3 scripts/stage_cpython.py
/usr/bin/python3 -m py_compile \
  scripts/stage_cpython.py tests/cpython_py1_smoke.py \
  tests/fixtures/cpython_py1/main.py \
  tests/fixtures/cpython_py1/helper.py \
  tests/fixtures/cpython_py1/stdlib_probe.py \
  tests/fixtures/cpython_py1/missing_import.py \
  tests/fixtures/cpython_py1/unhandled.py
/usr/bin/python3 tests/cpython_py1_smoke.py
```

`syntax_error.py` 是故意非法的负例，不进入宿主 `py_compile`。

## 边界与下一步

- 客体启动仍打印 `Could not find platform dependent libraries <exec_prefix>`；本轮
  测试不依赖 `lib-dynload`，但没有把提示隐藏或冒充完整扩展模块支持。
- 固定 hash seed、自旋 `time.sleep()`、无墙钟/安全熵/fork/exec/select/动态加载/
  线程等 0030 限制不变。
- PY1 没有验证传统 REPL、`input()`、Ctrl-D/Escape、JSON 存档、sync 后重启再读、
  峰值或完整标准库。这些仍属于 PY2 或后续独立 gate。
- 下一步按计划做 PY2：先验证空闲输入不被当 EOF，再做基本 REPL/input 和隔离盘
  JSON 存档的 sync/重启读取；不提前占用公共线程或 dash B2 范围。
