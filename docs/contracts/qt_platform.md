# Qt移植与系统底座协作契约

2026-10-28。接口责任与需求登记；受限 QtCore 客体资格见下文，不冻结尚未设计的C函数/ABI。
Qt具体版本、模块、feature、工具和资源预算在G01确定，不能把本契约当作任意Qt版本保证。

## 责任登记

| 能力 | 提供方/当前状态 | Qt侧责任与下一个验收 |
|---|---|---|
| C++/pthread/TLS | 工具链/线程线；T0–T2、T3-PY和Qt QThread受限测试有各自证据 | Qt配置与QThread/互斥/条件/退出探针；不复制第二套线程库或空锁 |
| 单调/墙钟 | 时钟SDK；单调等待与PY3 B2墙钟已有受限证据 | QtCore计时/超时与实际分辨率，唤醒deadline不被墙钟调整替换 |
| 事件就绪/唤醒 | QtCore受限 posted event/单调计时与跨线程唤醒已客体验证；通用多对象poll/select未实现 | E16需核实显示与跨线程组合等待；不得长期yield忙轮询或假报FD就绪 |
| 显示/输入 | 显示线；display_client、65/66、单surface/焦点、CPU raster与PS2 | QPA integration/screen/window/backing-store/input；读取实际mode/stride，客户端RAM呈现，不直接MMIO/BIOS |
| 内存/映射 | 内存线；堆/页预算已有，VMA/mmap/mprotect未实施 | 列实际调用与合法回退，提交最小失败探针；不从Qt侧另加内核mmap特例 |
| 文件/路径 | 文件服务+libc；现有受限FD/路径，权限/链接/完整locale未完成 | QtCore读写/资源/错误，明确ASCII路径边界；UTF-8内容不代表Unicode文件名合规 |
| 网络/终端/动态装载 | 各底座专项；无完整兼容资格 | 首窗不强制全量实现；关闭feature须可见并按实际消费者记录，不伪造成功 |
| moc/rcc/uic等生成器 | 移植线 | 首轮可同版本宿主生成、交叉构建；目标端重建另验G10，不混淆执行地 |

## 接口边界

- 内核只提供通用机制，不包含Qt类、对象名、程序名特权或Qt专属syscall。
- 用户态QtCore平台适配与QPA插件由移植线维护；现有src/ports/下新Qt目录在选型开工时建立。
  显示服务/SDK由显示线维护，pthread由线程线维护，公用libc/dispatch由整合负责人维护。
- SDK可用能力必须有版本/尺寸/布局、返回约定、错误与取消/超时、对象生命周期、线程并发
  和配额说明；具体ABI在提供方专项设计冻结。本表的“需要”不能直接当作头文件声明。
- 显示调用前完整校验源缓冲/区域；Qt不得假设零拷贝、直接Framebuffer映射或任意多窗口。
  输入序列/丢失重同步、焦点、客户端/服务死亡与等待唤醒沿用显示契约。
- 请求改变单surface、等待方式、共享映射或对象撤销语义时，先列新契约和旧消费者影响，
  不在QPA补丁里暗改底层行为。不要用新编号绕过必要的兼容与身份检查。

## 并行工作流程

1. 开工在state登记责任角色、分支、文件范围与最小gate；没有登记不能推定其他agent活跃。
2. Qt移植只修改端口/平台适配/自身构建与夹具；缺底座能力时提交调用点、输入、错误及预期。
3. ABI编号与服务op按abi_registry.md先登记，公共头/manifest/dispatch由对应负责人整合。
   号段预留防止跨模块重号，同段内仍需逐项登记；不抢PID/endpoint固定值。
4. 各自私有输出目录，SDK/构建输入固定；共享build排他。旧G02/T2/Python结果只佐证其原输入。
5. QtCore G03、首窗G04、Widgets G05、QML G06、Quick G07分别验；未实现/未运行/失败明确区分。

E15 已由 PR #8 合入 main（7a7481f）；E16 从该基线继续，新组合须独立记录输入与验收。

## E15 受限实现与资格

`codex/qt6-e15` 使用单消费者 coalescing wait-word 分发 posted events 和单调定时器；
FD/socket notifier 拒绝，不能与显示等待复用。QMutex 使用 pthread 单调条件变量；
QThread 取消、映射、路径 canonicalization、UID 权限及无覆盖 rename 不支持。
源码、竞态/生命周期限制与客体候选证据见 [0063](../work_log/0063_qt_e15_continuation.md)。
G01/G03 已受限功能通过，见 [0064](../work_log/0064_qt_e15_qualification.md)；绝对峰值和发行审计未完成。不据此开放新 ABI 或声明 poll 支持。
同一冻结实现的阻塞边界投递、伪唤醒/绝对deadline及活动定时器线程退出补验见
[0065](../work_log/0065_qt_e15_lifecycle_recheck.md)；未扩展公共机制或更改ABI。
