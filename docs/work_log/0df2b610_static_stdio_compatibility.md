# 恢复 raw native 标准流兼容并保持完整 FD 准入

R1 installer 的实际外部 native hello 没有 `.xos.exec` 标记。完整 FD 快照
接入后，glibc 普通 spawn 总会传入标准流描述符，加载器因此错误地要求所有
目标使用 v3 CRT。本组只修改静态加载器的内部准入分支，不改变公共 ABI。
规则见 [标准流兼容契约](../contracts/static_stdio_compatibility.md)。

`src/user/loader/load.cpp` 先区分 marker 确实缺席与 marker 检查失败，再验证
整个快照能否由既有 v2 路由精确表示。只有普通静态 spawn 可以降为 v2。
Files、额外 FD、清理项、状态标志、exec 替换及动态 pinned bootstrap 保持
原有拒绝边界。存在且错误的 marker 不能绕过该边界。

在 Preview 2 SDK 内执行：

```sh
python3 scripts/build_static_stdio_probe.py \
  --system "${XOS_SYSTEM}" --system-source "${XOS_SYSTEM_SOURCE}" \
  --output build/static_stdio_probe_v4
python3 tests/static_stdio_compat_guest.py \
  --system "${XOS_SYSTEM}" --system-source "${XOS_SYSTEM_SOURCE}" \
  --fixture build/static_stdio_probe_v4 --repeat 3 \
  --output build/static_stdio_guest_v3
```

原生系统 source 为 `3699916df590a2fe0ea9b419836ded2d9344e6b3`，build 为
`c1575e2adfc6fa5d`。构建器逐项校验该 immutable source 与完整 SDK，然后
将实际修复后的生产 `load.cpp` 显式链接进 probe，避免从旧 archive 取出旧
实现。严格 target 编译通过；loader source SHA 为
`6c67569169ab3dca4b84d7650c0345024dc632ca4649da51e08bbf42db816486`，
probe ELF SHA 为
`19c92eccf996154f2f9f5720985fb68c070753fbae3e1f92c35ebbf59c8001cc`。

15 项行为各执行三轮，45/45 通过，包括 12 次实际子程序启动。无 marker
目标接收 v2，有效 marker 目标接收 v3；真实管道读出 `DATA`，stdout/stderr
别名写出 `OUTERR`；关闭 stdin 的读取返回 denied。11 类负例均在 inspect
阶段返回 unsupported。每轮 supervisor 观察到的页、任务、完成记录精确恢复
为 `129779 / 2 / 0`；被拒绝的 Files 标准流对应文件在关机后离线读回未变。

保留的失败记录：第一次构建因测试使用未包含 initializer_list 的语法失败，
改为显式数组；前两次 guest 四项正例已通过，后因 probe 误向普通进程开放
的接口假设调用了 supervisor 专属资源统计而失败。移除该错误假设，保留
外层真实 supervisor 资源断言后取得本次完整通过。生产修复在这些 guest
尝试之间没有变化。失败不列作生产行为通过，也不覆盖原始 receipt。

本次是实际新 loader 与既有 c157 kernel/SDK 的组合验证。最终统一 source、
完整 native/静态 SDK、installer 外部 hello 与 GNU READY 修复的组合资格
尚待主任务重建和执行，不能把这里的通过转移到尚未运行的产物。

完整派生证据及原始失败记录见
[静态标准流资格报告](../reports/static_stdio_compatibility_20261128/README.md)。
导出保留原始 source/ELF/SDK 身份，实际 14 项构建与运行源文件另外逐一核对
`bddaf0fa4650beaacaa5094acca9def6c02e09e2` 的 Git blob；不把导出文件的
字节摘要替换成原始 receipt 的摘要。
