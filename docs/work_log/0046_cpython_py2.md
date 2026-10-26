# 0046：CPython PY2 基础交互与持久化

日期：2026-10-26

## 结果

PY2 客体 gate 6/6 通过。CPython 3.14.9 的 XOS profile 现在默认选择 basic REPL，
REPL 与 `input()` 共用端口内的控制台行输入：空 UART 读取继续等待，CR/LF 可分别
提交，Backspace/DEL 删除最后一个 UTF-8 码点，空行 Ctrl-D 产生 EOF。Escape 仍由
supervisor 强制取消前台进程，不冒充 Python `KeyboardInterrupt`。

同时验证了目录/文件操作、跨多次短读完整读取 3079 字节、预期的缺文件失败、
`math`/`re` 实际操作、UTF-8 JSON 写入，以及 `sync` 后关闭 QEMU、用同一临时盘
重启并读回 `雪 42`。未操作日常工作盘。

## 构建与证据

- CPython fingerprint：`c69e0fbf7772c775ab3e`
- profile：`py_t3_static_gil_pthread`
- 系统 build：`f25009cdbb27c857`
- 系统镜像 SHA256：`217519a93b16c23fe00237e3759ce72f5db83fa5878fe1c182fcb887eb1baa21`
- stage：560 文件；清单 SHA256
  `051707e4bf32c62293197348796fe1133b6f3509e6f2aad259f4cd91d9eb2504`
- stripped `/usr/bin/python3`：8,059,736 字节；SHA256
  `f1b9858b92d8f2d081c743fab9c3305870b7d9144fe5732e1609a4d9f6410fad`
- 报告：`build/cpython_py2_report.json`；SHA256
  `19aed309a6ad07e631514de2236ae239cfd0111ed20fc877ec322e0de7eec6a5`

六项分别为 basic REPL 空闲/复合语句/Ctrl-D、`input()` 空闲/退格、文件目录短读和
失败、JSON 保存、Escape 取消、重启读档。每项结束资源均回到
`[129833, 2, 0]`；普通退出回收 2864 页，监督取消回收 4238 页。

## 修改范围

- `src/ports/cpython/patches/0004_xos_basic_repl.patch`
- `src/ports/cpython/patches/series`
- `tests/cpython_py2_smoke.py`
- `tests/fixtures/cpython_py2/`
- CPython 计划、端口说明、状态和本记录

没有修改内核、公共 ABI、libc、files、loader、dash、xypm 或游戏代码；测试使用
独立 2 GiB 临时 FAT32 工作盘和隔离 CPython cache。

## 保留边界

基础 REPL 没有 readline/history/完整终端编辑，也没有 Ctrl-C/`KeyboardInterrupt`。
CR 与 LF 是分别验证的，不据此承诺 CRLF 组合的额外终端语义。路径仍按 ASCII-first
边界；UTF-8 内容已验，不推出 Unicode 文件名支持。无安全熵、墙钟、socket/TLS、
动态扩展、fork/subprocess 和完整 POSIX；XOS pipe 读仍为显式 `EAGAIN`。

PY3 按重要性与底座依赖另列于 [CPython PY3 可选扩展范围](../cpython_py3_options.md)。
