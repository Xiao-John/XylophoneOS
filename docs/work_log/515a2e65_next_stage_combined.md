# 515a2e65 · 固定闭包、Mobius 与 Pumpkin 合入后的普通客体

从干净主线 `515a2e65` 和锁定的 lwIP 2.2.1 源档重建普通镜像 `7d3b9663dc070599`。
QEMU 通过 79 项常规检查，覆盖启动、进程、文件、持久化、满盘和运行时。
另通过 10 项许可材料检查，ABI 登记与源码一致，共有 78 个已分配 syscall。
回执绑定源码树、2071 个构建输入、系统和 SDK 清单、ISO、lwIP 源档与 QEMU。
[证据索引](../reports/next_stage_515a2e65_20261127/manifest.json)

共享 libc 固定闭包、Mobius QtGui 单对象替换和 Pumpkin 的双 UID 封存登录分别有
专项工件和客体回执。普通镜像复验覆盖这三项合入后的常规开机配置。
[固定闭包](glibc_d2_fixed_runtime_loading_policy.md) ·
[QtGui 替换](05dfb2b9_mobius_qt_v2.md) ·
[Pumpkin 部署登录](pumpkin_sealed_credential_input.md)

```sh
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" make smoke PYTHON='python3 -B'
python3 -B tests/docs_consistency.py --output-dir build/ordinary_docs_check
```
