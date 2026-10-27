# Shell、执行与文本：实现摘要

截至2026-10-27。当前行为以implementation/shell.md、implementation/make.md和xsh.md为准。

## 实现

- xsh原生默认入口，exd为exec-driver别名，PATH含/usr/bin；命令解析、候选探测、ELF装载、
  权限与启动分层。轻量提示/错误诊断不改变Shell权限；不自动安装/bin/sh。
- dash 0.5.13.5：A简单脚本与同步spawn；B0/B1受限子构造权与真实GCC/G++子工具链；
  B2继承共享打开描述、wire v2、0–2重定向/dup/close及builtin恢复。
- C1阻塞管道、<=4096字节小写原子性/背压；raw旧句柄ABI保留短写。
  C2单线程eager-copy fork隔离、子Shell、命令替换；C3匿名HereDoc和同PID exec。
- C3当前SDK v3/.xos.exec完整32FD分组与CLOEXEC转交；旧未知CRT继承文件stdio/exec明确
  ENOTSUP，不能靠path重开补身份。单线程profile，线程fork/exec未交付。
- 最多4段前台管道、fork深度3、命令替换stdout1MiB、argc/env各64、startup16KiB；
  用户重定向0–2，底层exec保留0–31。后台、异步信号、trap/jobs/wait/kill内建仍拒绝。
- UTF-8文本/argv通道U0/U1已有专项，ASCII路径边界不因文本支持自动取消；U2路径未验。
- 固定sbase Make使用-B串行图，已实测XOS内构建Make及C/C++；完整增量/规则另补。

## 证据与边界

| 输入 | 结果/入口 |
|---|---|
| B2 build911184be3f3c99f6 | B2 6/6、B0/B1 7/7、process/SDK13/13；build/dash_b2_acceptance_report.json等 |
| C3实现e729dc6、build2f7160b7d6633ee6 | 22个串行入口passed；C3主66、exec16、atomic7，完整输入见[冻结资格](../reports/dash_c3_20261026/qualification.json) |
| C3 xos.img | SHA256 5deb880b9479ce7b155a24362fe97a7290938112244da4d41b3ebffbba1b0a1d |
| C3 SDK | 普通d531a24b2f679c8ae4b96fd6cb18127bb42a0798ac306152a4c90d362764e393；线程8cf47213690c2dbe95719c087cb1f84b456ddc06b9f2b7987940b00d4a747444 |

C3资源baseline=end=[129826,2,0]；旧失败/候选SDK与report-only erratum保留，未以跳过
旧stdio边界或修改成功输出伪造通过。不承诺完整POSIX/GNU Make、SMP、任意迟到RPC恢复
或长期压力。早期“没有管道/fork”等仅适用于当时A/B阶段，不是当前限制。

## 合并来源

原文按[source_index.json](source_index.json)记录的提交、路径和SHA256恢复；以下锚点保留旧引用。

<a id="log-0024_shell_port_scout"></a>
- `docs/history/shell.md#log-0024_shell_port_scout`
<a id="log-0025_dash_a"></a>
- `docs/history/shell.md#log-0025_dash_a`
<a id="log-0026_xshell_alias_confirmation"></a>
- `docs/history/shell.md#log-0026_xshell_alias_confirmation`
<a id="log-0027_xsh_execution_ui"></a>
- `docs/history/shell.md#log-0027_xsh_execution_ui`
<a id="log-0028_dash_b0_b1"></a>
- `docs/history/shell.md#log-0028_dash_b0_b1`
<a id="log-0033_utf8_text"></a>
- `docs/history/shell.md#log-0033_utf8_text`
<a id="log-0042_dash_b2"></a>
- `docs/history/shell.md#log-0042_dash_b2`
<a id="log-0046_dash_c1_pipe_wait_wip"></a>
- `docs/history/shell.md#log-0046_dash_c1_pipe_wait_wip`
<a id="log-0047_dash_c1_implementation"></a>
- `docs/history/shell.md#log-0047_dash_c1_implementation`
<a id="log-0048_dash_c2_isolation"></a>
- `docs/history/shell.md#log-0048_dash_c2_isolation`
<a id="log-0049_dash_c3_script_exec_make"></a>
- `docs/history/shell.md#log-0049_dash_c3_script_exec_make`
<a id="source-shell_port_scout"></a>
- `docs/history/shell.md#source-shell_port_scout`
<a id="source-upstream_dash_c1_c3_review"></a>
- `docs/history/shell.md#source-upstream_dash_c1_c3_review`
