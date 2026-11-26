# abf0fc0a · CPython 与 GNU 共享 C++ 合入后的普通客体回归

从干净主线 `abf0fc0a` 重建普通镜像 `8863999ce1a57285`。QEMU 通过 79 项
普通客体检查，覆盖启动、进程、文件、持久化、满盘和运行时。10 项许可材料与
ABI 表检查通过。回执绑定此次源码、ISO、普通 SDK、lwIP 和实际构建工具。
[普通组合回执](../reports/next_stage_abf0fc0a_20261127/manifest.json)

这次回归覆盖普通开机配置。CPython 的统一 glibc SDK 安装、GNU C++ 固定依赖闭包
和 ClarkE 原生 HTTPS 分别使用各自的构建材料和专项回执。glibc 发行默认、共享 C++
工作线程和 WebCore 整页继续各自验收。
[CPython](4d321863_glibc_cpython_unified_stock.md) ·
[GNU 共享 C++](glibc_d2_shared_cxx_fixed_closure.md) ·
[ClarkE HTTPS](clarke_native_https_transport.md)
