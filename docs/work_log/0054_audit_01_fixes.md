# 0054：audit_report_01 四项修正与当前证据绑定

2026-10-26。用户要求按audit_report_01修正；基线为本地main cb26f7b。
本线独立实现，不派代理、不推送、不更新0.0.1-1026或日常盘。原审计正文保留原基线
结论，只在末尾追加本批回执。新代码Apache-2.0，没有引入第三方依赖。

## XOS-A01：单文件恢复失败关闭

修改src/user/services/files.cpp：

- remove_if_present只接受FR_NO_FILE/FR_NO_PATH为缺失，不把读取错误当成功。
- journal/target/backup/temp检查区分错误与缺失，完成全部存在性/类型预检后才修改
  恢复材料；journal读取检查close与长度。错误锁定recovery_failed，普通请求返回io。
- 同步恢复结果后清理temp/backup，再同步，最后删除journal并同步。每步失败立即
  停止。删除后最终flush失败时尽力重建marker，仍返回失败；持续坏盘下不保证重建成功。
  unlink报错时不再写坏可能仍存在的日志。没有声称任意掉电/扇区撕裂安全。
- 正常replace先验证目标/身份，随后才创建journal；失败应用保留日志/材料并锁定，
  不走忽略清理结果的成功分支。正常完成复用同一受检查的清尾步骤。
- staging的close/清理错误也锁定；f_sync失败后仍调用f_close，不遗留已失去追踪的打开对象。

确定性宿主测试直接include生产files.cpp，链接真实FatFs及Unicode适配，只有SDK
调用和FatFs API错误入口被测试夹具控制。21项覆盖journal/target/backup/temp stat、
read/close、unlink、rename、三次flush、缺失journal路径及正常提交/回滚/缺失对照；
断言io门禁及journal/有效数据保留。此测试不是客体硬盘故障注入。

真实客体5项：孤立temp清理、backup回滚、第二次启动幂等、已提交target清尾、损坏
journal拒绝stat/mkdir且保留全部输入；逐文件由只读FAT后端检查，资源[130337,2,0]稳定。

## XOS-A02：当前ABI表与定义

e04_loader_sdk.md当前维护编号改62/23/24，旧54/20/21明确标为合并前历史；PR #2
的sys54/file op20–22保持不变。新增tests/abi_doc_consistency.py从共享头核对当前
专用表8项，包括sys_random_bytes=63；不扫描改写历史报告/编号或重新设计ABI。

## XOS-A03：当前入口与历史分开

- xos_plan的T0–T2/T3-PY及dash B2/C1–C3改为各自已有受限gate，并保留T3-QT未验。
- state改为一份简明当前摘要；原cb26f7b全文与Git blob标识保存到
  docs/history/state_cb26f7b.md，原工作记录、报告及哈希不动。
- next_release记录1026已发布/实际资产，后续准备另列；0050的“源码尚未提交/待确认”
  标为发布前历史，并指向db5b46c与既有发布回执。总览同步，不把旧结果改绑新源码。

## XOS-A04：SDK/系统/运行库的身份绑定

新增scripts/sdk_receipt.py与config/release_cpp_runtime_v5.json；修改构建SDK元数据、
系统manifest、package_release.py和release_smoke.py：

- SDK文件摘要来源于系统manifest已有sdk/ artifacts；新增精确目录清单。验证完整
  文件集合/空目录/摘要与manifest中的build、ABI、target、configuration、single运行模型。
- C++头/归档/来源manifest绑定到已验v5单线程快照的完整树及manifest摘要。不是新
  线程SDK登记，不因SHA一致就宣称普遍ABI兼容或发行者认证。
- 所有输入先验，再创建发行输出；存在staging目录直接拒绝。拷贝后再次验证源输入
  未变化，逐项核对实际SDK与运行库拷贝，不拿成品自算摘要替代输入对应检查。
- 发行manifest新增sdk_binding：输入SDK、配置摘要、完整运行库来源、最终SDK树。
  成品树仅排除自引用release.json，并显式记录该排除；资格runner核对相同输入/成品。
- 老SDK缺configuration等绑定字段时明确要求新构建，不回填或替换已发布1026的回执。

11组宿主检查：正确集合、修改/缺项、残留文件/空目录、混合manifest/symlink、错误
build/target/ABI/config/runtime（即使文件哈希被重绑定）、旧无绑定输入、运行库更换、
拷贝偏离、成品篡改；实际打包CLI对坏SDK在生成输出前拒绝，输入文件集合/摘要不变。
另用本轮真实SDK+已锁C++运行库在build/audit_01/sdk_composition私有组合，核对输入与
成品的完整对应。没有重建/发布完整发行包，不据此认定1026曾发生错配。

## 实际命令与最终回执

```sh
python3 tests/file_recovery_faults.py
python3 tests/release_sdk_binding.py
python3 tests/abi_doc_consistency.py
python3 scripts/build.py --output-dir build/audit_01/system
python3 tests/file_recovery_guest.py
python3 tests/package_p2_maintenance.py --system build/audit_01/system --output build/audit_01/maintenance_final
python3 scripts/license_audit.py --build build/audit_01/system
```

宿主Python3.12.15、GCC/G++16.2.0、QEMU11.1.2，FatFs错误夹具由Apple clang编译。
最终build **e78fbff3985357f3**，kernel385084字节；xos.img SHA256
`44f1551140474c60bbe6478604a379e6e8fc9d4106de48e910c0c9b0295a80bf`。

- 宿主恢复21项：build/audit_01/recovery/report.json。
- 实际恢复5项：build/audit_01/recovery_guest/report.json及各case串口日志。
- SDK绑定11组：build/audit_01/sdk_binding_tests.json。
- 当前ABI表8项：build/audit_01/abi_doc_report.json。
- 维护9项：build/audit_01/maintenance_final/maintenance_report.json；资源[130337,2,0]
  前后一致。包含fork/exec/anonymous新路径、非零/故障/Escape后门禁及恢复重新准入。
  新探针SHA256 `815360a3d6f8632b7cc2d7d5efa9eee488ce5723c5d6c30f461fa784bd120b7e`。
- 真实SDK组合：build/audit_01/sdk_composition/receipt.json。
- 许可材料7份：build/audit_01/system/license_report.json，成员级追溯仍开放。
- 总回执：build/audit_01/final_receipt.json，绑定最终系统/SDK/源码/测试/报告摘要，
  保存已完成与未运行的区别。旧355fecd维护报告不改绑，当前来源疑问用新回执解决。

首次中间候选0de590bfc7ab25fc也通过当时的专项；随后收紧journal unlink失败时不
覆盖既有日志的策略并补实际CLI负例，统一重建为上述最终版本后重跑受影响检查。
没有把中间结果当最终版本，也未在失败时降低验收标准。

未运行：硬件I/O故障/任意掉电/扇区撕裂、P2-2 guest/共享畸形输入差分及完整ELF、
P2-3、多成员法律审计、旧全量或长压力。共享build、冻结SDK、旧资产、日常盘和
localpilot保持隔离。修复保留工作树供复核；本批无剩余编辑/构建占用，未推送。
