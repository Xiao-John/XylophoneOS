# FB1/FB2 受限验收证据

本组正常系统build `32fe73250f191e04`，冻结输入和文件摘要见 `qualification.json`。
`acceptance.json`记录14项真实客体/宿主端到端结果；`sample_bundle/`是由客体生成、
经sync/重启后验证的四文件样本，`binding.json`绑定本次运行ELF和符号ELF。
`system_manifest.json.gz`记录实际源码/工具/产物，ELF与镜像留在本地私有build。

各`*.serial.log.gz`是对应真实QEMU串口；`process_report.json`和`file_report.json`
是同系统E04/E05回归；`host_writer.log`和`host_symbols.log`是宿主定向检查，不代替
客体故障证据。`attempts/invalid_demo_expectation`保留旧夹具错误假设；混杂的旧构建日志
仅为历史失败排查，不作为最终构建证据。本次最终构建使用单独目录和单独日志。

本组仅对本地代码和上述输入的受限范围成立；没有发布版本、没有PR，不推出全系统收集、
真实硬件、任意断电、并发配额原子性、后台/孙进程、日志或完整core已通过。命令、
保存/导出边界和后续见[0081](../../work_log/0081_fb1_fb2_fault_bundle.md)。
