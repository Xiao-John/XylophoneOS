# 0033：UTF-8 文本通道 U0/U1

2026-10-25。用户要求为 dash/xsh 落地 UTF-8 文本接口，并把输出/读取解码与原生
多语言输入分开；主目标是在客体里用原生 G++ 编译运行 `UNICODE_example1.cpp`。
本组占用 `src/user/include/xos/text.hpp`、`src/user/programs/supervisor.cpp`、
`src/ports/dash/console_xos.cpp`、`scripts/build_dash.py`、新增 UTF-8 测试与夹具、
`docs/utf8_text_plan.md`、本记录和 `state.md`/索引；串行执行一次共享 `make build`
并重建 dash。没有修改文件服务/FatFs 路径、libc locale、内核控制台、进程 ABI、
CPython 或发布镜像。

## 交付

新增 [utf8_text_plan.md](../utf8_text_plan.md)：把文本通道、路径编码、locale 和
原生输入法分成 U0/U1、U2、U4、N1；本组只做 U0/U1。

实现：

- 新增 `xos::text`：增量 UTF-8 解码、整行校验、显示宽度、按码点退格。
- Xsh：行编辑接受高位字节，退格按码点和宽度擦除；Enter 前拒绝非法 UTF-8；
  分词仍只按 ASCII 空格，回显仍按原始字节。
- dash：控制台适配复用同一套解码/退格/校验；非法行丢弃并提示；空闲读从
  `EWOULDBLOCK` 立即返回改为 yield 重试，修掉 `sh: turning off NDELAY mode`
  刷屏。
- dash 构建默认使用当前 `build/sdk`（冻结 0.0.1-1024 SDK 缺少 B0 的
  `xos_posix_spawn_driver`）；`build_dash.py` 增加仓库 include 以取共享头。

## 证据

系统 build `3d7665a665df9443`，`build/xos.img` SHA256
`74b07888492ed1c4c7b2117fcb42568d77a5523715df5375af7e86bfb7842b12`。
资源/旧压力未重跑。

- 主目标 `build/utf8_example1_native_report.json`：客体原生
  `/usr/bin/x86_64-elf-g++ -static --sysroot=/sysroot` 编译
  `tests/fixtures/utf8/UNICODE_example1.cpp`，运行输出逐字节匹配：
  `Wir müssen wissen, Wir werden wissen.\n我们必须知道，我们终将知道。\n`。
  源码 SHA256 `cd9eedac3ce2b385aa530b401cd96b746a9daddeef1d4c3608e2ebdb987901ef`，
  期望串 SHA256 `14b38975d7e57f46476f0cd7aea723c7c1ba9702808a79eeeac0ec9a519cfd2e`；
  seed 174 文件、sysroot 1036 文件。
- `build/utf8_text_report.json`：Xsh 6/6 — UTF-8 回显与参数、按码点退格、宽字符
  两列擦除、非法序列整行拒绝、UTF-8 argv 传给客体程序、超长行拒绝。
- `build/utf8_dash_report.json`：dash 4/4 — UTF-8 回显、退格、非法序列、退出回到
  Xsh。dash ELF SHA256 `a5053d4ea955a3784eaba717835efa1463a8beac9dcf8959d20228408a03f765`
  （fingerprint `e083d1dc680f42b8000c`）。

## 明确未做

- 文件名/目录/`stat` 的 UTF-8：`files.cpp` 仍只允许 ASCII，U2 未开始；测试里
  `xsh: /usr/bin/你好: cannot read program` 是当前诚实结果。
- VGA 不渲染 UTF-8，串口是当前文本界面。
- 没有 UTF-8 locale/字符级 `?`；dash 仍按字节匹配。
- 没有 native 输入法/键盘；宿主终端或粘贴送来的字节才算输入。
- 未新增语言包或包管理器；建议只做只读数据包+工具，见计划文档。

## 下一步

1. U2：文件服务/FatFs 接受并校验 UTF-8 路径，列目录不再跳过非 ASCII；
   同步放开 `work_disk`/测试夹具。
2. L0（可选）：只读 Unicode/本地化数据包 + 查询/生成工具，不做安装器。
3. U4：UTF-8 locale、精确宽度、字符级 glob。
4. N1：客体键盘与输入法，等显示/GUI 底座。
