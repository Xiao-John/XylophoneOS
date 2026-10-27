# Dash 当前受限支持范围（C1–C3已验收）

C1/C2/C3已按顺序独立验收，最终22个串行入口全部通过，build2f7160b7d6633ee6，
见0047–0049与docs/reports/dash_c3_20261026/qualification.json。
支持最多4段前台流水线、真实单线程fork隔离（深度3）、builtin/函数/子Shell、
$()与backticks（raw stdout上限1MiB）、Here-document（引用/展开/<<-与大正文）、
带完整32FD/CLOEXEC的当前SDK v3目标exec；不是完整POSIX Shell。Shell用户重定向
仍限定0–2，标准C exec机制保留0–31。argc/env各64；spawn单串255、exec单串4095、
startup总16KiB，进程全局8个；资源不足明确失败与清理，不承诺任意长度/深度。

后台、trap/jobs/wait/kill等信号/作业内建继续明确拒绝；取消为前台Escape机制，
没有异步POSIX信号、SMP或线程profile fork/exec承诺。旧静态ELF可普通console spawn；未知/旧目标继承普通文件stdio明确拒绝，
显式exec未带`.xos.exec`标记的旧CRT返回ENOTSUP，不丢FD后继续冒称兼容。
正常外部命令仍走已验spawn；`exec`内建和Make后端才使用真实替换。

直接脚本兼容由Dash在用户态处理：无shebang或/bin/sh、/bin/dash、/usr/bin/dash
且无额外interpreter参数的文本可fork后exec当前Dash；其他shebang明确失败。
不创建/bin/sh文件别名、不替换Xsh/default Shell。Make选定sbase固定c546c3a的
显式-B串行profile，详见make_subset.md；没有增量时间戳/并行/GNU Make全兼容声明。

以下保留A/B0/B1/B2历史回执，旧拒绝项已被新阶段支持替代，不表示当前又禁用了它。

## 构建与兼容

独立程序安装为/usr/bin/dash，不替换xsh或自动创建/bin/sh。构建入口scripts/build_dash.py，
固定source lock/patch和匹配SDK；普通console旧ELF仍可spawn，继承文件stdio与exec须通过
当前CRT身份准入。sbase工具与Make独立stage，不用宿主执行冒充XOS运行。

旧SDK可用范围由当时profile决定，当前可执行标记不允许忽略CLOEXEC/文件会话后继续运行。
构造权按父进程可信委派，不从文件名/PATH搜索结果自动授予；Escape沿前台等待链取消，
不是POSIX信号。FD与启动大小限制见上表和e04_loader_sdk.md，资源不足报错并回滚。

## 证据

各阶段实现和完整旧输入统一见[Shell历史](../history/shell.md)，最终冻结C3资格在
[reports](../reports/dash_c3_20261026/qualification.json)。新组合0059仅重验相关路径，
不改绑C3或宣称后台/完整POSIX/任意压力完成。后续见[路线](../plans/dash.md)。
