# CPython PY3 可选扩展范围

2026-10-26，0046。PY0–PY2 和 T3-PY 已通过；PY3 不是一个必须整包完成的阶段，
而是一组各自有依赖、许可和客体 gate 的可选扩展。以下按朋友能直接获得的价值、
对公共底座的侵入和验证成本分档。任何一项都不能因“模块可导入”自动算通过。

0049进度：A1选定闭包已在XOS客体实测通过，覆盖hashlib已知向量/HMAC、pathlib、
argparse、dataclasses、tomllib、decimal、XML和固定时间戳的未压缩zip；当时`statistics`
因导入`random`时无系统熵而阻塞，原报告保留该历史结果。0052完成B1后，更新解释器
可通过系统熵使用这些随机接口。A2 zlib 1.3.2已静态
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

## B 档：重要，已按独立范围完成

1. **安全熵（B1 已完成）。** `sys_random_bytes=63` 通过 x86-64 RDRAND 产生至多
   256 字节；`getentropy()`如实报告硬件不可用或失败，不从TSC、计时器或固定种子造熵。
   CPython客体验证了`os.urandom()`、`random`、`secrets`和`statistics`，并在QEMU关闭
   RDRAND时确认调用失败。熵质量仍依赖CPU/虚拟机实现；没有virtio-rng路径。详情见
   [0052工作记录](work_log/0052_cpython_b1_entropy.md)。
2. **墙钟与时区（B2 已完成）。** PC RTC 提供启动时UTC epoch，PIT仅用于之后单调推进；
   QEMU设置UTC。CPython POSIX TZ规则、ZoneInfo与锁定tzdata 2026.5通过客体gate。
   RTC只在启动时取样，VM暂停期间没有外部RTC刷新承诺。
3. **SQLite 静态模块（B3 已完成）。** SQLite 3.54.1自定义XOS VFS，客体通过建库、
   提交/回滚、唯一约束、busy、损坏输入及sync/重启/完整性检查。范围限单进程、单个
   可写连接和rollback journal；无WAL、共享内存和跨进程锁。
4. **其他压缩格式（B4 已完成）。** `_bz2`使用bzip2 1.0.8，`_lzma`使用liblzma
   5.8.4，`_zstd`使用zstd 1.5.7；三者分别通过有界流式roundtrip、截断/损坏输入与
   资源回收gate。zstd损坏校验探针显式启用帧checksum。

B2、B3、B4均绑定同一CPython fingerprint和SDK，报告/限制见
[0058工作记录](work_log/0058_cpython_py3_b_segment.md)。B段不代表完整POSIX时钟、
跨进程SQLite并发、完整压缩生态或任何新发行版已经发布。

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
