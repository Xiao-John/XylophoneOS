# 0048：xypm P2-1维护准入与失败关闭

2026-10-26。用户要求派子代理完成ISO扩容并继续xypm下一阶段。本线在主agent实现
P2-1；ISO由子代理独立完成0047，CPython PY2继续由外部移植线负责。

## 已实现

- `process_abi.hpp`追加sys54 `sys_process_guard`与16字节owner/worker查询，不变更
  sys38–52线程操作或sys53 ISO payload。tasks.cpp只提供通用进程准入：监督独占，
  begin必须无其他应用/构造中进程（files除外），屏障内仅允许创建一个worker，
  拒绝其create/grant/delegate。end/rearm只在worker已死后允许，PID仍不重用。
- files v2布局不变，追加op20/21与SDK Client方法。files从kernel查询真实guard，
  指定worker且全局无打开实例/staging才能取写租约；没有租约不能写。屏障/租约
  生效时其他会话只能读，不能write、write-open、replace、remove、mkdir、rename、sync。
  只有监督owner可释放，释放前确认打开实例/staging清空并同步块设备。
- supervisor新增`maint-run`、`maint-recover`、`maint-status`。worker成功0后清理释放；
  非零、异常、Escape或清理失败保留屏障。recover重新交接worker时始终保留准入，
  恢复程序不可用或失败继续锁定，不默默恢复普通启动/写入。
- 新程序名不赋予权限；任意普通进程包括dash都不能取得监督控制或释放租约。
  当前只能退出dash回Xsh后进入无其他应用的维护；普通xypm查询仍两Shell共用。

核心范围：tasks.cpp、process_abi.hpp、file_abi.hpp、file_client.hpp/cpp、files.cpp、
supervisor.cpp，新增tests/package_p2_maintenance.py与fixtures/package_p2/maintenance_probe.cpp。
不修改线程生命周期算法、CPython/dash端口、包容器或日常工作盘。为ISO协调把
boot_payload外部声明改const指针；ISO子代理负责其实际存储与页保留（0047）。

## 实际验收

先隔离构建`python3 scripts/build.py --output-dir build/package_p2_system`，build
500e882e1aa928d9、kernel360508字节，xos.img SHA256
5533164160299113e79e9015fea24c61b51153c049e63e500beb8cc39ae7df1f。
`python3 tests/package_p2_maintenance.py` 8/8通过，资源前后[130345,2,0]。

八项为：普通控制拒绝/普通写允许、缺程序释放空会话、后台普通进程阻止进入、
独占worker写租约且不能spawn、非零后失败关闭/恢复、故障后失败关闭/恢复、
Escape后失败关闭/恢复，以及最终sync后的真实文件/被阻止路径检查。每个模式均
验证新启动与监督mkdir被阻止、只读cat可用、错误恢复路径不能解锁、正确恢复后
普通程序/写操作恢复；不只检查打印的成功文字。

失败过程：首个fixture用strcmp但只链接freestanding libxos，链接拒绝；改用现有
sdk::equal/length，保留不带libc的最小探针。首轮测试期望kill旧marker `killed=`，
实际接口为`kill: accepted`，程序已正确终止；按实际输出修正测试，记录
build/package_p2/first_failure.json。没有因此修改kill语义或冒称失败通过。

最终还在0047正常kernel输出`build/iso_capacity/normal`重跑本组8项，以绑定两线
同一核心源码；最终回执/哈希见下节及build/package_p2/final/maintenance_report.json。
旧压力、全量回归、完整线程SDK资格未重跑。

## 当前边界与下一步

这是P2-1，不是完整P2。探针只写/out的测试标记，不装包、不升级/卸载或改写/usr。
持久包journal、旧文件备份、幂等回滚/清尾、重启恢复门禁和原生ustar/JSON/SHA256
校验尚未交付；客体xypm写命令继续关闭，P1宿主候选盘事务仍可用。内存guard不
能充当断电/重启恢复承诺。恢复器退出0是当前监督工作会话的约定，正式xypm恢复
工具必须先真实检查journal再返回0，不能用无条件成功程序代替。

接续P2-2：原生有界包/数据库验证与只读计划，共享P0/P1畸形夹具；P2-3：持久
intent/staging/backup与启动恢复门禁，逐步中止、正常sync/重启检查；P2-4：这些
通过后开放install/upgrade/remove/recover，分别记录两Shell查询与维护进入体验。
P3签名/仓库、任意扇区撕裂/长压力仍另验。见package_management.md和维护命令页。
本组未提交/push或发布release，localpilot未读/未改。

## 最终共同构建回执

0047正常kernel build4c79f3a789dcff61上，本组8/8再次通过，资源仍[130345,2,0]。
镜像SHA256 4950c4c2fb53c36ac7cf36d4b6e40954c5b36507f8fc11207b867b54520b16ee；
探针SHA256 ab1ba10f6852e55b4026a2b30e05c90ad4924bc4084b06050cd5cc9e3c485df2。
实际命令：python3 tests/package_p2_maintenance.py --system build/iso_capacity/normal
--output build/package_p2/final。当前全部270份src/摘要与该manifest匹配；最终
receipt在build/package_p2/final/final_receipt.json，同时绑定测试源码、系统manifest、
ISO子线receipt与许可报告。license_audit.py --build build/iso_capacity/normal通过
7份已登记材料，第三方预构建库成员审计仍是原有未完成项。

核心实现/测试占用解除，无剩余构建。本批后续不自动重建共享build或更新新release；
build/iso_capacity根的容量probe产物仅用于验收，正常候选在其normal/子目录。
