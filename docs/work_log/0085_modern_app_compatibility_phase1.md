# 0085 现代应用兼容平台第一阶段

2026-10-29，独立`codex/modern-app-phase1`，基线upstream `39083f9`。
本轮没有完成N2 TCP/HTTP；PR #18无review、未合入，公共device机制实施BLOCKED。
PR #19/#20保持独立Draft/open。原工作区、作者、冻结证据、发行资产都保留；不自合并main。

实际交付：可交叉构建并在XOS执行的真实QuickJS解释器probe（显式两处源适配）、
原Code扩展宿主script及原LocalPilot前端bundle的真实失败探针、重新构建的
CPython线程/SQLite/zlib候选及依赖运行/失败矩阵、受控HTTP宿主夹具、三份独立兼容报告和N2接续包。

文件范围：`scripts/modern_apps_*`、`tests/modern_apps_*`、`tests/fixtures/modern_apps/`、
`licenses/modern_apps/`和组件登记、`docs/reports/modern_apps_20261029/`、本日志及state。
无内核、公共ABI/libc/Qt/N1/Aurora功能修改；没有第二套Agent Runtime或模拟浏览器/IDE。

详细构建命令、实际输入/SDK/ELF/镜像/工具SHA、QEMU命令、串口、资源和失败见
[冻结证据入口](../reports/modern_apps_20261029/README.md)。
三项报告分别是[Chromium](../reports/modern_apps_20261029/chromium_compatibility.md)、
[LocalPilot](../reports/modern_apps_20261029/localpilot_compatibility.md)、
[Code OSS](../reports/modern_apps_20261029/code_oss_compatibility.md)。
下一步及严格依赖顺序见[N2](../reports/modern_apps_20261029/n2_network.md)。

关键失败保留：初始QEMU私有可执行动态链接失败；GNU工具调用环境/宿主assembler误选；
QuickJS原版malloc/tm字段及runtime链接失败；256KiB预算超过XOS128KiB栈导致客体vector14并被内核回收；
夹具重复mkdir；Pillow单元缺上游构建宏；宿主缺setuptools；模块Promise拒绝未计失败的早期测试器缺陷。
最终探针收紧为64KiB栈并显式检查拒绝；错误退出与父Shell精确资源回收分别断言。
未执行、阻塞、兼容失败与测试器成功复现失败严格分列，不把负例转为应用通过。

许可证：新自研代码Apache-2.0，原QuickJS/Code及Python依赖条款原样保留。
只做受限本地探针，不发布浏览器、LocalPilot、Code或新XOS发行版；逐成员/产品静态分发审查未完成。
