# 239f7e42 · dash glibc 预览执行原生 ELF

显式选用 glibc C SDK 的 dash 预览启用现有前台命令路径。dash 处理带斜杠的路径和
自身的 PATH 查找，再通过原生 `posix_spawn`、`waitpid` 启动并等待。本机 `access(X_OK)`
负责查询格式，加载器负责实际启动时的 ELF 检查和权限判定。

普通前台命令使用原生标准流。文本脚本的 fork/exec 回退、显式 exec、管道、子 shell、
命令替换及 here-document 保留各自的现行能力边界。完整 C3 仍需继续验证。

## 门禁

[预览来宾门禁](../../tests/dash_glibc_preview_guest.py) 从普通 xsh 和现行 dash 脚本
启动同一预览 ELF。测试 ELF 校验 `argv[0]`、带空格的参数、空参数、环境与工作目录。
显式路径的子进程返回 0，PATH 查找的子进程返回 23。两条入口分别验证缺失命令返回
127、文本 ELF 格式错误返回 126，以及无创建权限的预览返回 126。

xsh 权限负向走普通 `exec-file` 入口。现行 dash 权限负向通过测试启动器运行同一个
预览程序，并在启动前清除该子进程的创建权限。每项检查前后比较页、进程和完成记录
基线。旧版预览的 builtins、文件读取、拒绝管道和 here-document 等场景随同运行。

## 结果

使用合并后的候选 C SDK，从本次源码重建正常 BIOS 系统。QEMU 11.1.3 中 xsh 和
现行 dash 各通过 11 项，22 项均恢复资源至 `[129698, 3, 1]`。关机后回读预览写入的
文件并核对字节。`tests/dash_pipeline_fds_test.py` 也通过。

先构建常规版再构建预览版。常规 newlib dash 与冻结基线逐字节一致，后续普通
安装镜像的隐式选择仍嵌入该 ELF。首轮未留下可读来宾报告，以下结果来自同一源码重跑。

| 验证绑定 | SHA-256 |
| --- | --- |
| 系统 `4601516f6b5ac549` 的普通 ISO | `b369f2db02d7ffd7ba67f6cb90d3475f557969a3e1d95f72dfc83a7994217ae2` |
| glibc C SDK manifest | `e6fd644f5c8717ea67877fb58d6ed1118703913d3ce77fc70e05cd98ffb2ab58` |
| 预览 ELF | `afdee96906e9475aff83bb3e1b0f3321a0bb3aabf18a2e8429c3029d944ff98d` |
| 预览回执 | `002610c58cb9e9a176967c6a1de3c1ff394b24d0a0373fa71084e407fba7367f` |
| 常规 newlib ELF | `94be9cc12698f6da03be0737e938f0c3d1f42061c3f89f3bcec869fcfc191067` |
| 普通安装回执 | `518b76238dfbaaf45712adcffbe6ab72213caefa12728c3a6d609fe3cb9ed41a` |
| 来宾报告 | `8459bd734b60b33dfb1fbea83cb3012be934afdaa0d63f454ab2503359088722` |
| 串口 | `c384204dffb8d7703ed0a9df212d5a160ab30d36b6949814cd141fe43f600957` |

## 主线冲突复验

切换到合入进程修复后的主线 `db8e15dd` 时，自动合并保留了旧预览的
外部命令拒绝分支。真实客体验证在首条外部命令返回 126。保留常规 newlib 入口并
恢复预览的原生 spawn 后，从 `fff643bb` 的源码重建正常镜像。xsh 和 dash 共
22 项通过，每项恢复 `129698 / 3 / 1`。常规 dash ELF 摘要仍为上表所列。
此次针对进程变更的新签名 SDK manifest 为
`1d516751a2169d525a6f3328a7904a1d248d7b2d4d739b5752dd3af6bed27335`。

| 复验输入 | SHA-256 |
| --- | --- |
| 系统 `fb33ca87475cd129` manifest | `02145f1f82c6dd7ad1bce564bb8bec473f0a2aa5f5069fb2734dc1ac97a90b79` |
| ISO | `58886f902f18fb4ad6c64807580cac2c7d9aeedfd806ff2a270a38b77db933cf` |
| 系统 SDK manifest | `09e592e86e99cb29e45afeb95fba9289ef19c0789c914573d7eac827863402e2` |
| glibc profile | `dd863ea5c10d8799db7cf498a36dab8ec8121e2a0c847ebb01c7ca92d9b3e9a6` |
| glibc dash 构建回执 | `3603d424453738286b62dbe472ad2a61bba269422f067028488abb5deb8a7d59` |
| QEMU 报告 | `ca5539727292324b2ad1d200281dd500d7426c465e54fbeb8b645a247329664a` |

一轮并行构建期间的独立启动门禁未在时限内观察到损坏引导拒绝标记。
本表只记录启动到正常 xsh 后的 dash 复验结果。
