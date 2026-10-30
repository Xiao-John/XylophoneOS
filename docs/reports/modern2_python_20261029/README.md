# Python 静态 Pillow：真实核心能力与并发阻塞

2026-10-29。**单线程静态 Pillow 核心在 xsh/dash 真实客体通过。Pillow threaded use 为 UNSUPPORTED / BLOCKED。**
早期真实 dash worker 在 newlib `_malloc_r` 发生 vector14，根因尚未解决。
最终少量对照未复现不能消除旧失败；LocalPilot 服务使用线程，本结果不提升为 Core 可用。

输入基线 upstream `aaec2e9d8ffe61ce1d523cd56852d36cde3edd07`，独立分支
`codex/python-static-imaging`。最终系统 build **ec4b7ffa0c53f5a4**，
CPython **d2d064e8db8332bc7d91**；这是兼容性候选，不是发行版。
构建/安装路径见[实现说明](../../implementation/cpython_pillow.md)。

## 实际通过的公共能力

Pillow 11.3.0 官方源包 SHA256 与 76 个上游核心 C 源、全部217个 C/头/Python 文件
锁定于 `src/ports/cpython/pillow/source_lock.json`。原始 C/PIL Python 源零改；
CPython 3.14.9 真正静态链接 `PyInit__imaging`，以 `PIL._imaging` 注册并安装原包。
只新增可选构建/安装胶水，不新增 syscall、内核、libc、安全绕过或第二套 Runtime。

| 本轮行为 | 实际结果 |
|---|---|
| xsh、dash 导入/版本/静态注册 | PASSED；同一真实 XOS ELF 与原 PIL 包 |
| 已知16×16 RGB字节、翻转/裁剪/最近邻缩放、差分 | PASSED；完整768个原始字节有预期值 |
| PNG/zlib、BMP 文件写入/关闭/重开/逐像素往返 | 两入口 PASSED；导出真实文件由独立宿主 Pillow12.3.0 再解码并比对全部字节 |
| 截断PNG、负尺寸、默认图像炸弹防护 | PASSED：真实拒绝；未取消默认防护 |
| 错误退出、之后再运行 | 两入口错误状态符合预期；xsh恢复通过；资源精确返回 |
| 原始依赖观察收集 |20项：PIL.Image、localpilot_service、localpilot_service.protocol真实导入通过；其余17项失败 |
| 资源 | 核心及最终诊断每操作均回到 free=130279/tasks=2/completions=0；不是绝对峰值或长压力资格 |

[最终公开回执](guest/report.redacted.json)、[资格与实际产物](qualification.json)、
[独立宿主解码](host_decode.json)。导出PNG SHA256
`a71a482cb9b7b7b95d0970d90a67f8fff29b3121fb96474bc7e7b4879f672948`；
BMP SHA256 `76895d2586036597e46a3fc4e73482576e7edadca2d5e63d1d7352d4584c026c`。
原像素 SHA256 `098eac87305cc0f96b14e264312587bf236f960644366c5b617453e188863053`。

## 真实并发失败与后续归属

保留的[早期客体回执](failures/guest-attempt2/report.redacted.json)中，dash 先成功导入并
写出相同PNG/BMP，随后 worker **tid20**（exec主线程tid17）在 `_malloc_r` 写 top chunk
header 时 vector14：RIP `0x4037927b`，CR2 `0x60cc5fc8`，newlib
`libc/stdlib/_mallocr.c:2597`。该次回收5938页后精确回到基线。原串口未捕获 RSP，
不能补造。故障记录在该次原镜像/脚本上，未改绑最终系统。

最终镜像重新实际运行了原 `T3_PY_CORE`（Lock/RLock/Condition/Event/Queue）两入口、
CPython+zlib 两线程对照两入口、PIL 两线程40次往返两入口，以及 dash 内的现有 xos-diag
包装。7个有限诊断本次均通过、精确回收，诊断包装本次没有故障包。
**没有修复 allocator，也没有证明故障仅来自 dash、exec 或 Pillow。**
下步由线程/newlib/exec生命周期负责人复现并检查分配器锁、sbrk/trim与线程身份关系；
需要记录失败现场和 heap 状态后再决定修复。本分支不越界修改这些公共运行时。
并发Pillow与在线LocalPilot仍BLOCKED，不能把本次未复现当线程安全或应用资格。

## 仍然失败和未验

原始 pypdf6.1.1/filters 导入仍在 `_posixsubprocess` 依赖失败；fcntl、select、selectors、
subprocess、_socket、_ssl，以及依赖它们的原始 Agent 权限/策略/Schema、service安全/工作区、
CLI/API入口均失败。`O_NOFOLLOW`+owner-only创建真实报 EINVAL；未降级普通open、未改UID/mode。
私有 LocalPilot 来源只读 main `9a21ebbe6621de43be6568b64433230c317eb81a`，原工作区保持干净。

JPEG/JPEG2000/TIFF/WebP/AVIF、FreeType/LCMS/RAQM/imagequant/Tk 后端未集成；
存在其他纯Python插件不构成资格。动态扩展、所有Pillow API、映射文件、屏幕捕获、
长并发/压力、完整 Agent Core/API1.0、身份、Operator审批、UNKNOWN、真实网络/HTTPS及发行
均未因此通过。N2按未合入PR #18继续BLOCKED。没有修改macOS安装或正式发行包。

## 冻结材料与隐私

- `inputs/`：最终系统/系统SDK、实际使用的独立线程SDK、stage清单、Setup与真实生成注册表。
- `build/`：最终系统构建、完整CPython配置/编译/链接命令和输入回执；早期失败保留。
- `guest/`：最终两入口结果、逐操作资源、QEMU命令、版本和实际图像；`failures/`保留初始归档路径错误、
  Setup变量/版本引号/嵌套object目录错误、首次重复mkdir及真实客体fault。
- [工具回执](tools.json)与[实际命令](commands.json)；未沿用旧“通过”。冻结前再次验证全部675个系统源码、
  CPython构建器/端口及实际SDK逐文件SHA精确匹配。

**`*.redacted.*`是脱敏公开副本，不能称为无损串口副本。** 原始依赖traceback会打印私有源码行，
公开副本只移去这些帧的源正文，保留文件路径、行号、函数、错误；完整原始日志、串口、工作盘和
真实ELF仍本地保留，其绝对路径/字节数/SHA256列于qualification。没有上传私有源码或可执行产物。
没有私有内容的单项日志和构建日志以无损gzip保留；完整许可证在端口和实际stage中。
许可材料审计通过只代表材料完整，不是静态产品发行或逐成员法律资格。

交付前同步上游PR #24到`169f51e`，仅两份原则文档；已阅读C28用户态驱动、C29唯一单调时基。
Pillow无驱动/计时机制改动；N2需按新原则重审，仍BLOCKED。真实测试输入仍上述冻结源码与镜像，
未将文档同步冒充运行重验。再次核对675个系统源码SHA保持一致。
