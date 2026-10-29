# 0079 应用故障包与音频输出计划

2026-10-29，基线 `94f8e30`，分支 `codex/fault-bundle-audio-plans`。
用户要求分别编写两份计划；本组仅文档，不实现功能、不分配ABI、不更新发行资产。

## 范围与交付

- [应用故障包](../plans/app_fault_bundle.md)：FB0勘查/格式、FB1客体最小报告、
  FB2离线定位、FB3可选快照/日志、FB4用户交付。覆盖单一wait、权限/身份、
  同一装载实例摘要、格式/配额、保存失败、符号匹配与真实客体gate。
- [音频输出](../plans/audio_output.md)：AU0勘查、AU1单音机制、AU2服务/旋律、
  AU3可选PCM、AU4 WAV、AU5消费者。覆盖PIT channel隔离、有期限的发声权、
  强制静音、服务生命周期、QEMU捕获、DMA安全及各阶段验收。
- 更新 `docs/README.md` 索引和 `docs/state.md` 的计划状态；新增本文。
  不改源码、共享头、ABI登记、宪法原则或冻结reports/releases。

## 源码依据与选择

`process_status` 已含故障vector/address/instruction，现有wait按真实父PID查询并
在成功复制后消费完成记录。另起收集器再次wait无法取得同一结果，因此首版接在
原消费者后，普通xsh直接子进程先行；不承诺dash孙进程或全系统覆盖。
`load.cpp`持有文件版本进行装载，计划要求同一实例摘要，避免故障后路径已被替换。
完整寄存器、error code、故障TID和栈不是当前公共状态；可选增强另做授权/版本设计。

当前PIT channel 0承担调度时钟；PC Speaker计划使用channel 2且不得改channel 0。
单靠服务sleep后stop不能避免服务挂起时长鸣，因此计划要求有上限的设备租约和
可验证的静音路径。声卡、PCI/DMA和WAV是独立后续，现有设备代码不算音频已实现。
现有QEMU运行器没有显式音频配置，捕获探针命令仍标候选，没有冒充实际输出证据。

两项均保留内核机制/用户态策略边界；接口号、服务权限、错误与资源生命周期在
对应勘查阶段冻结，本文不私占保留号段，也不建立新的用户逐接口审批流程。

## 验证

仅文档检查，未构建新系统、SDK、应用或音频产物；没有新的build ID、ELF哈希、
故障包、声音捕获或客体验收。未重跑旧全量smoke/Qt资格。

环境：Python 3.12.14、Git 2.52.0；命令在仓库根目录执行：

```sh
python3 tests/docs_consistency.py --output-dir /workspace/xos-env/logs/plans_docs
python3 tests/abi_doc_consistency.py --output-dir /workspace/xos-env/logs/plans_docs
git diff --cached --check
```

检查通过：430个本地链接、66个已分配syscall与73份历史来源一致；当前ABI速查与
源码一致，暂存差异无空白错误。JSON回执在上述外部输出目录；该目录不进入Git。
计划中的命令、gate和预算均不是已运行记录；文档检查不构成运行时功能资格。

## 接续与限制

本组结束后无文件或公共build占用。下一位可分别开展FB0和AU0，先登记自己的文件
范围/私有构建目录，再用真实探针冻结接口、预算和失败语义。
FB0优先查单一wait接入、同实例摘要与文件服务失效；AU0优先查QEMU WAV路由、
PIT隔离、授权及到期/退出静音。源码实施另用独立分支/PR，不因本文存在自动派工。
故障快照、新设备机制、PCM或第三方库均未实施；不把规划视为已交付资格。
