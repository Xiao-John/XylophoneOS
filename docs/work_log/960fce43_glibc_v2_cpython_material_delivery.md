# 960fce43 · CPython 重链接归档暂存

CPython 重链接归档与同一发行的 SDK、profile 和实际 CPython XPK 绑定。暂存器
从冻结包归档读出 XPK，核对其发行摘要，再读取包构建回执，核对接收材料里的
调试解释器、去除调试节后的解释器、剥离配方，以及实际 `usr/bin/python3`
的字节数和摘要。

在 [GNU Make 暂存命令](960fce43_glibc_v2_gnu_make_material_delivery.md) 后追加
`--cpython-relink "$CPYTHON_TAR" --cpython-manifest-sha256 "$CPYTHON_MANIFEST_SHA256"`。

断网 Linux 用 `960fce43` 的实际发行执行。CPython 重链接归档原样进入外层
清单 v6，大小为 34,036,201 B，SHA-256 为
`9e3b36125d26f46e93e06e3f07a4f79dc351e0503fffed3f126170e7f9d93c20`。
接收者目录按完整校验表核对 15 项。错误清单、来源于不同 XPK 的材料及与冻结
解释器不符的材料被拒。省略新增参数重现此前 v5 暂存结果。
[实际外层清单和回执](../reports/glibc_v2_cpython_material_delivery_20261127/manifest.json)

同一候选的 CPython 原版与替换版均通过普通客体检查。zlib、gzip、DEFLATE ZIP、
zipimport 和错误退出行为与原版一致，替换标记实际出现。
[CPython 原版、独立接收和替换客体](960fce43_glibc_v2_cpython_relink.md)

这个冻结候选的 17 个 glibc 静态程序有接收方重链接及替换客体记录，覆盖 xypm、
Dash、13 个日用程序、GNU Make 和 CPython。GNU Seed 原生编译器供体和最终产品
仍需按各自范围验收。正式发布待发行门完成。
