# CPython PY3 可选扩展范围

2026-10-26，0046。PY0–PY2 和 T3-PY 已通过；PY3 不是一个必须整包完成的阶段，
而是一组各自有依赖、许可和客体 gate 的可选扩展。以下按朋友能直接获得的价值、
对公共底座的侵入和验证成本分档。任何一项都不能因“模块可导入”自动算通过。

0049进度：A1选定闭包已在XOS客体实测通过，覆盖hashlib已知向量/HMAC、pathlib、
argparse、dataclasses、tomllib、decimal、XML和固定时间戳的未压缩zip；`statistics`
因导入`random`时无系统熵而阻塞，保留在清单中，不伪造熵。A2 zlib 1.3.2已静态
集成，gzip、deflate ZIP、zipimport及损坏/截断输入客体gate通过。完整报告见
`build/cpython_py3_a1_report.json`、`build/cpython_py3_a2_report.json`和
[0049工作记录](work_log/0049_cpython_py3_a1_a3.md)。A3选用无依赖的`idna 3.20`
纯 Python wheel，已通过离线 `.xpk` 打包、哈希校验、xypm 候选盘安装/卸载、客体
真实导入与 IDNA 编解码；错误 wheel 哈希和原生 `.so` 成员均被拒绝。A3 首版边界为
单个锁定的`py3-none-any` wheel、校验`RECORD`、只安装到 CPython 3.14 的
`site-packages`，不生成 console script，不支持依赖求解、在线 pip、venv 或原生内容。
证据见`build/cpython_py3_a3_report.json`和0049工作记录补充。

## A 档：优先，直接扩大可用面

1. **已构建模块的标准库闭包验收。** 先用已在静态解释器中的能力做已知向量和实际
   操作：`hashlib` 的 SHA-2/SHA-3/BLAKE2 与 HMAC、`pathlib`、`argparse`、
   `dataclasses`、`tomllib`、`decimal`、`statistics`、`xml.etree`，以及未压缩
   `zipfile`。这一步风险最低，也能给后续包分发一份真实模块矩阵。
2. **zlib 静态模块。** 它同时解锁 gzip、deflate zip、压缩 zipimport 和常见 wheel
   载荷，收益最高。需冻结上游源码/许可并验压缩、解压、截断及损坏输入；不能因
   宿主 Python 有 zlib 而代验目标模块。
3. **离线纯 Python 包。** 先支持固定哈希和清单的 `py3-none-any` 包，由 xypm 安装
   或回滚；不承诺在线 pip、venv、源码构建隔离或 manylinux 二进制 wheel。

推荐顺序是 **A1 → A2 → A3**。A1 可立即开始；A2 完成后，A3 对现实包的覆盖面会
显著增加。三项均保持在端口/分发层，不要求先扩张内核接口。

## B 档：重要，但先补真实公共底座

1. **安全熵。** 提供可审计的系统熵后，才能移除固定 hash seed，并开放
   `os.urandom()`、`secrets` 和随机 UUID；伪随机或 uptime 不得冒充安全熵。
2. **墙钟与时区。** 真实 Unix 时间、校时来源和时区数据分别验收；现有单调 PIT
   tick 不能冒充墙钟。这是可靠时间戳、证书有效期和更多 `datetime` 操作的前提。
3. **SQLite 静态模块。** 固定 SQLite 源码和许可，验证建库、事务、并发 busy、
   损坏/容量失败、`sync` 后重启读取；不能只验内存数据库。
4. **其他压缩格式。** `_bz2`、`_lzma`、`_zstd` 各自冻结依赖并单独设 gate；优先级
   低于 zlib，不把其中一个通过写成“压缩完整”。

## C 档：生态扩展，依赖更大的系统能力

- **受限 subprocess/spawn。** 必须先定义 XOS 的参数、环境、描述符和退出语义；
  无 `fork` 就明确只提供可实现的 spawn 子集。当前 pipe 读会返回 `EAGAIN`，所以
  `posix_spawn` 存在本身不能推出 `subprocess` 可用。
- **socket 与 TLS。** 先有网络栈和 socket，再有安全熵、墙钟、证书库和 TLS；不得
  用关闭证书验证作为通过路径。
- **完整终端交互。** readline/history、方向键、Ctrl-C/`KeyboardInterrupt`、信号
  和终端属性需要真实控制台/中断契约。PY2 的基础行编辑器不声称覆盖这些能力。
- **UUID。** 名称型 UUID 可较早单独验收；随机 UUID 必须等待安全熵。

## D 档：暂缓，成本高且不是首批朋友使用所需

- 动态扩展加载、`dlopen`、`ctypes`/libffi 和原生 wheel。
- `multiprocessing`、完整 asyncio 网络/selector/signal 支持。
- venv、在线 pip、联网构建和构建隔离。
- free-threaded CPython、JIT、多解释器并发与 SMP 性能承诺。

## 共同验收边界

每个 PY3 项目都要保存目标产物指纹、静态/纯 Python 模块清单、上游许可、客体中的
实际调用、失败输入、退出状态和资源回收。涉及持久化的项目还要在独立临时盘执行
`sync`、重启和重读。涉及安全或网络的项目不得用固定种子、宿主结果或跳过验证来
替代目标系统能力。PY3 不阻塞已通过 PY0–PY2 的首次 PY4 分发收口。
