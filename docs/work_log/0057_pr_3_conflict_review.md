# 0057：PR #3合并冲突检查

2026-10-27（Asia/Shanghai）。用户仅要求检查主要冲突，不逐行审计，不执行合并。
PR：https://github.com/Xiao-John/XylophoneOS/pull/3

## 检查输入与结论

检查头为`f84745a9079be23b5ae959fb7bc927837e2a6294`，远端目标与共同祖先为
`5b4e5e13a15234209cc42f1ba09d5b240cb78043`，本地main为
`cb26f7bde6aabcea0ad4cc087621322ef1bee8f9`，并包含尚未提交的审计、CPython和文档改动。
GitHub只读API在检查时报告mergeable=true/clean；这只描述远端目标，不涵盖本地工作树。
PR共78文件、11提交，主题为E14显示backend/PS2/服务。

**不宜原样整合到当前本地开发线：存在P1级ABI冲突，另有5个文本冲突文件。**

## P1：sys63/64重复分配

PR的`src/shared/include/xos/display_abi.hpp:5`定义sys_display=63和
sys_display_present=64；`tasks.cpp:2223`在常规switch前拦截这两个编号。
本地process_abi.hpp已有sys_random_bytes=63（已提交B1），工作树另有
sys_clock_realtime=64（PY3 B2实现中）。tasks.cpp可自动合并，但调用会先被显示分发
接走，使熵/墙钟进入错误协议；不能靠解决文本冲突消除，也不能假定编译会报重复case。

建议保留已经采用的63/64，为显示从整合时的空闲编号另行分配；同步显示共享头、SDK
manifest、测试、当前ABI文档，并重建相关SDK/客体。PR旧冻结报告保留其原编号与输入，
新的整合资格另记录，不机械改旧证据。新编号在真正整合时检查后确定，本轮不占号。

## 文本冲突与保留事项

`git merge-tree --write-tree HEAD refs/review/pr_3_head`表明，本地已提交main相对PR有
3个冲突：docs/decisions.md、docs/e04_loader_sdk.md、docs/state.md。

进一步把共同祖先、当前工作树文件、PR文件送入临时目录的`git merge-file -p`，
8个重叠文件中5个出现冲突，另3个可文本自动合并：

- 冲突：上述3个文档、scripts/run_qemu.py、scripts/user_build.py。
- 可自动合并：docs/xos_plan.md、src/kernel/arch/x86_64/tasks.cpp、src/kernel/include/xos/platform.hpp。

手工合并需同时保留RDRAND CPU设置、PY3 B2的UTC RTC参数、显示VGA设置；SDK生成器
同时保留审计新增configuration/runtime_model及显示扩展字段（含修正后的编号）。
当前state已重整，并含审计/POSIX/CPython任务信息，不能整份用PR旧状态替换。
ABI文档保留维护62/file23–24、熵63及墙钟64，再补显示记录。

## 方法与未运行项

优先调用GitHub连接器失败后使用公开只读API与git fetch；取回PR到本地review引用，
未checkout、stash、stage、commit、push或修改实现。merge-tree只生成临时合并对象，
merge-file输出只在宿主临时目录处理，工作树未写入冲突标记。

没有重跑PR已有测试/压力或完整构建，没有逐行安全/正确性审计；上述判断只针对所列
输入的冲突风险。整合修号并解决冲突后，应定向复核熵、墙钟、显示、SDK manifest和
受影响启动路径；旧PR回归成绩不能代替新组合验收。本轮未向GitHub提交review/comment。
