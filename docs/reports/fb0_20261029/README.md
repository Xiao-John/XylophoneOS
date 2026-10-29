# FB0 冻结证据

本目录绑定正常系统 build `6c2e83dfaa2737bb` 和独立故障注入系统 build
`084024c841126499`；清单/文件摘要见 [qualification.json](qualification.json)。

- `guest_report.json` / `guest_serial.log.gz`：正常系统五项客体检查。包括测试型装载器
  open包装：在返回装载器同一持有句柄之前，完整读取ELF并计算SHA-256、复位偏移，
  然后运行未修改的装载器；不是已实现的生产回执。
- `service_exit_report.json` / `service_exit_serial.log.gz`：独立注入系统中的文件服务
  #UD退出；在途stat返回-8、后续ping返回-7、监督终端可继续处理stats。不是正常系统
  自然故障、自动恢复或未执行请求的证明。
- `process_report.json`、`file_report.json`、`full_disk_report.json`：当前正常构建的
  原有E04/E05/E07定向回归。`e04_fixture.txt` 是给原E04提供临时FAT盘的执行入口。
- `host_client.log`：宿主替身测试，单独验证无回复时8192次循环及发送失败，不代替客体。
- `system_manifest.json.gz`、`service_system_manifest.json.gz`：实际源码/工具/产物
  哈希与命令。大体积ELF和镜像保留在各自本地build，未上传发行资产。
- `attempts/`：无盘维护阻断、注入未触发和串口只读到前缀的历史失败，均未计入通过。

复现命令、范围与限制见[工作记录](../../work_log/0080_fb0_fault_bundle.md)。报告不覆盖
生产故障包写入/解析、任意断电安全、完整core、全系统收集、服务自动重启或物理磁盘。
