# 0059：PR #3与本地新改动兼容整合

2026-10-27（Asia/Shanghai）。用户授权先本地兼容，之后由用户squash PR并提交本地改动；
本组不提交、不推送、不修改远端分支/PR。另按用户新要求，今后开发改走独立分支/PR。

## 输入、范围与保留

PR #3头f84745a9079be23b5ae959fb7bc927837e2a6294，共同祖先5b4e5e1，本地main
仍cb26f7b。先在build/pr_3_compat/before.zip备份本次触及的先存文件，输入摘要与新增
路径记入integration_inputs.json。仅将PR的78个路径三方整合到工作树，未改HEAD/index。

5个冲突文件手工保留两侧内容：decisions/e04/state采用追加且保留当前摘要；run_qemu
同时保留RDRAND默认CPU、VGA和UTC RTC；user_build保留configuration/runtime_model
及显示扩展、模块追加与gfxdemo链接。tasks/platform三方合并保留B1/B2/维护机制。
0054审计、0055包校验、0056契约及0058 CPython/许可修改均保留，localpilot不进入扫描。

## ABI决策与SDK

保留已经由CPython B段使用的sys63熵、sys64墙钟，将显示控制/呈现改为65/66。
这样不使刚验收的静态CPython程序失效；PR显示SDK/程序则须由当前源重建。早先0057
建议移动显示，此处正式执行；用户可原样squash现有PR，修号在之后本地提交中体现。
当前文档、普通SDK与线程SDK生成器的display_extensions均为[65,66]。未覆盖冻结SDK，
没有把PR原始63/64报告改成65/66。旧PR显示二进制不能用于新组合内核。

增强abi_doc_consistency检查跨共享ABI头的数字编号唯一性，并增加可指定输出目录，
避免改写旧审计回执。新增tests/pr_3_compat.py验证新组合的共享分发和资源生命周期。
不重跑旧全量/长期压力；SDK打包身份检查因生成字段合并而定向回归。

## 验证入口

```text
python3 tests/abi_doc_consistency.py --output-dir build/pr_3_compat
python3 scripts/build.py --output-dir build/pr_3_compat/system_final
python3 tests/pr_3_compat.py --system build/pr_3_compat/system_final --python-work .cache/xos_seed/cpython/11c39c52e451a9499450
python3 scripts/license_audit.py --build build/pr_3_compat/system_final
python3 tests/release_sdk_binding.py
```

另以宿主clang编译运行boot_info_cases（当前boot_info.cpp），检查v1/v2合法/非法头边界。
报告与最终结果在本记录后续补齐；旧0058/G02资格仍只对应各自原输入，不改绑。
本轮没有重建完整CPython、线程C++ SDK或公开发行包，不声明那些新产物的资格。

## squash之后如何提交本地内容

当前工作树已含PR实现，本地HEAD仍cb26f7b。不能在脏工作树上直接pull后期待自动解决。
用户完成GitHub squash后，应先fetch并确认origin/main确实含所审PR内容（若PR头变化，
先重新核对）。保留当前cb26f7b的备份分支/引用，再使用`git reset --mixed origin/main`
对齐基线：此命令仅重置HEAD/index，保留工作文件；不要用--hard、checkout覆盖或clean。
确认状态只剩本地审计/CPython/契约及本轮兼容差异后，再由用户选择提交。

这一步**尚未执行**：等待用户完成远端squash。本地未提交文件和build备份仍应保留。
后续新任务按Discipline使用codex/分支和PR，本轮遵守用户已有的提交安排。


## 最终结果

最终build **76a2e4380f64fb2e**，kernel430140字节，独立输出
`build/pr_3_compat/system_final/`；xos.img SHA256
`a6554ffbad566a12f6645b4b259e64c94c41b50123e1b7a1be6de0ffba374ed6`。
7组新组合检查通过：源码/SDK/ABI绑定、显示前后的既有CPython熵/墙钟、显示权限与真实
线程、软盘/两种ISO的23项显示检查及回收、无RDRAND的真实不支持失败。没有重跑完整
G02像素/键鼠/异常矩阵或B2–B4全部用例，不能称本组合完整重新验收这些历史阶段。
12个ABI表项与跨ABI编号唯一性、boot_info宿主边界、11项SDK绑定、7份许可材料通过。

最终manifest的全部源码与产物哈希复核一致，回执`build/pr_3_compat/final_receipt.json`。
PR78路径中68个保持原样，其余10个为上述本地实现/文档兼容差异；明细保存在
pr_file_comparison.json。线程SDK生成器已同步显示字段，但本轮未重建完整线程/C++ SDK。

首次组合测试已实际输出正确熵/墙钟标记，但测试未开启xsh trace，等不到诊断退出行而
误报超时；修正为expect_supervisor(trace=True)，重建到system_final后重新运行通过。
原失败日志保留failed_attempt_1，原build7120e476镜像保留system/，未覆盖为最终成绩。

HEAD仍cb26f7b，index未变、工作树未提交、未推送；0059占用已解除。后续新开发按用户
要求走PR。用户完成远端squash后再按上述步骤核对/对齐基线，不直接pull覆盖工作树。


后续：用户已squash #3并授权创建本地工作PR；0060完成基线对齐，详情见
[0060](0060_pr_3_squash_alignment.md)。上述未提交/等待状态保留为0059当时记录。
