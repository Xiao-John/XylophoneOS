# 7698198a · QtBase backingstore 着色器可重生成

2026-11-27 · 基于 #310 `23cd4d2d`。核对上游 QtBase 6.8.3 原档内两份预编译资源。
提取 `.vert`、`.frag`、发布 `.qsb` 和 `REUSE.toml`，五份内容与 QtBase `v6.8.3`
对应 Git blob 一致。两份 `.qsb` 最近一次上游变更为 `d2fcccd3`。QtGui `CMakeLists.txt`
从 QtBase 发行目录读取预编译资源。源声明及出现在现有套件和外部示例中的位置已登记。
[QtBase 官方摘要](https://download.qt.io/archive/qt/6.8/6.8.3/submodules/qtbase-everywhere-src-6.8.3.tar.xz.sha256) ·
[QtBase 上游变更](https://github.com/qt/qtbase/commit/d2fcccd3f1c5e3729c280a6f0a3e12dc9835477b)

## 生成与比对

先用套件实际 Linux arm64 qsb 6.8.3 的 `--qt6 --qsbversion 64` 从 GLSL 生成 QSB v6。
两个包共 12 个后端，另含两份反射。5 个文本后端及反射对每个着色器均字节一致；两份
SPIR-V 仅第 3 个字的生成器标识有差异，原档 `0x0008000a`，当前工具 `0x0008000b`。

取得 Qt 6.4.0 Linux x86-64 官方 QtBase、Qt Shader Tools 和 ICU 包，三份压缩包均
与 Qt 发布 SHA-256 一致。另核对官方 6.4.0 Shader Tools 源包中 glslang 生成器版本
为 10。官方旧 qsb 运行于断网 Linux x86-64，动态库来自同版 Qt 归档和签名 Debian 软件源
的 13 个已记录依赖包。用 `QT_HASH_SEED=0` 和明确的 GLSL、HLSL、MSL 参数从 GLSL
重建，两份反射和 12 个后端全部逐字节相同。现代 qsb 对旧工具生成包及发布包的解读一致。
[Qt 6.4.0 二进制包目录](https://download.qt.io/online/qtsdkrepository/linux_x64/desktop/qt6_640/) ·
[Qt 6.4.0 Shader Tools 源包摘要](https://download.qt.io/archive/qt/6.4/6.4.0/submodules/qtshadertools-everywhere-src-6.4.0.tar.xz.mirrorlist)

用现代工具重新写出 Qt 6.4 序列化格式。操作中插入的是从刚重建的包中提取的同一份
SPIR-V。顶点直接复原。片段剩余差异是 HLSL 与 MSL 的两个映射各自采用不同的写入次序。
按发布包采用的绑定键 `1, 0` 次序重写这两个映射后，片段也原样复现。用冻结源码在新输出
目录重复完整配方仍通过。片段重排序入口会拒绝顶点包。
[已实测的命令与分发声明](../../src/ports/qt6/quick/backingstore_shader_distribution.md)

| 资源 | 重生成与上游原档共同的 SHA-256 |
| --- | --- |
| `backingstorecompose.vert.qsb` | `e5e191ff1f94085d082b5d73417945fc312f178a27dbce884390f9d838fb5231` |
| `backingstorecompose.frag.qsb` | `2c4b5b7415b6dfa562615ed9a836e2c8f16087ca2e381faa1b1a05972ce06c1b` |

## 成品与声明

从目标、宿主两份 QtGui 归档的 ELF 资源读回两个 payload。未替换与双库替换的外部示例 ELF、
套件宿主 qsb 可执行文件各自含原档载荷一次。两种源声明和所交付的许可文字分别绑定。套件共用
的 GPL-3.0-only 与 Qt GPL exception 文本和原 Qt Shader Tools 6.8.3 归档逐字节一致。历史
上游作者的实际构建命令与环境仍缺记录。最终成品的许可分支选择、传递许可、安装信息及发行渠道
仍按实际分发组成核对。
[证据索引](../reports/qt_quick_backingstore_shader_replay_20261127/manifest.json)
