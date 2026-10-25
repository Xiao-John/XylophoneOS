# 0025：E09发行交付收口，可选dash A

2026-10-25。用户授权接第一段dash，并明确Xshell/xsh继续保留原生Shell定义权；
dash仅作为用户从Xshell启动的独立程序。E09发行交付完成，朋友独立试用、备份恢复
与升级不覆盖源码的实际记录仍待补；不将O19/O20改标通过。

新增ports/dash原包锁、完整COPYING、本地后端、补丁和显式构建入口；保留上游
解析/展开/控制流。spawn/wait同步执行普通程序；无默认入口替换、无/bin/sh别名。
只修改files.cpp一处已暴露根路径拒绝；没有改内核或SDK ABI。
licensing登记dash，未构建或引入BusyBox。详情shell_subset.md。

实际构建scripts/build_dash.py，配置/源码/SDK隔离到.cache/xos_seed/dash/；最终ELF
962344字节，SHA256 97dd273e34924203bad691df02b3f4f13e3fd448571c84d2065335c05fb7072e。
manifest在439a3c7825a15e276be9。首次构建强制include污染mkbuiltins数据，后改为
该生成步骤排除profile声明；其余目标使用本地profile。去除无权限模型的ownership
测试路径，文件读写/可执行检查使用真实access；无signal stub注入libc。

首次客体在外部探针printf %zu处故障（strlen/0x9）；%d有界长度探针通过，格式支持
另待根因核查。随后cd /tmp→/暴露files根路径尾斜杠拒绝并定向修复。
使用Python导入scripts/build.py，将BUILD显式置为ROOT/build/dash_system，串行构建
64fcf112f8efc899；记录.cache/xos_seed/dash/system_build.log，没有改共享build镜像。

实际执行：

```sh
python3 tests/shell_smoke.py --manifest .cache/xos_seed/dash/71318ebaced6d868b1df/manifest.json --system build/dash_system
```

16项客体检查通过，资源基线[130342,2,0]逐组恢复；覆盖脚本、-c、-i、argv空字符串/
引号、环境、状态、控制流、cwd、缺失命令和五种不支持语法拒绝。71318与最终439a3
ELF摘要完全相同，不因构建脚本指纹变化重复运行功能测试。报告在71318目录、串口
build/dash_a_serial.log。没有运行旧回归/压力，也没有将16项推广为完整POSIX兼容。

过程中发现并发的历史文档移动和supervisor PATH修改，未覆盖或提交对方文件。
64fc系统manifest的supervisor源码哈希与Git HEAD发布版一致，后续PATH修改不同；
因此新PATH行为不在本次证据内。当前工作区整体尚未统一构建验收。

下一步按B补重定向/编译器授权/取消，或独立改善xsh交互；用户选择哪种Shell。
本组完成后不保留编辑占用，未提交推送，未修改发行标签/附件或日常工作盘。
