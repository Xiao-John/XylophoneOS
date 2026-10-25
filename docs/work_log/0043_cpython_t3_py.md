# 0043：CPython T3-PY 救火（阻塞 I/O gate）

2026-10-25。首次客体 T3-PY 为 4/5：线程原语、线程异常、daemon 退出和非
daemon 关机等待通过；失败项暴露 XOS `pipe` 读当前是显式 `EAGAIN`，不是
阻塞 pipe，不能拿它证明 CPython 在 I/O 等待期间释放 GIL。本组只修 T3-PY
gate，不修改内核/公共线程 ABI/libc/files，也不把 XOS pipe 改成阻塞语义。

## 修改

- `tests/fixtures/cpython_t3_py/blocking_io.py` 使用真实文件服务：
  `open("/work/t3_py/io_payload.bin", "rb", buffering=0)`，每次 `read(4096)`
  走 files RPC，不再依赖 pipe。
- 主线程在每个 4 KiB 块返回后采样后台线程进度；要求至少 3 个 I/O 窗口内
  后台进度前进，而不是只看首尾 `after > before`。
- 保留后台线程、GIL/pthread、资源恢复和 Python 退出检查。

## 证据

- `python3 tests/cpython_t3_py_smoke.py --work
  .cache/xos_seed/cpython/cebe2527e705a185b6b9 --image build/xos.img`
- build `911184be3f3c99f6`；image SHA256
  `d9b81936924e729d2cf059d936b2406828a6785c151246603ed77ec9b2c5121d`；
  fingerprint `cebe2527e705a185b6b9`。
- `build/cpython_t3_py_report.json` 5/5 passed；五项资源均恢复为
  `[129833, 2, 0]`；`T3_PY_BLOCKING_IO_OK`。
- 未运行的检查：阻塞 pipe 行为（XOS 仍显式 EAGAIN）、SMP、真实墙钟/
  高负载 GIL 竞争。

## 边界

这是“GIL 在 files RPC 等待期间可被后台线程取得”的客体 gate，不是完整
POSIX 阻塞 I/O 或 pipe 语义验收。pipe 的 EAGAIN 仍应在调用方按非阻塞处理。
