# 14a518fa — 审计后续：构建来源、运行库与图形流程实装

2026-11-12。基线 `158a9b99550c03b97e74e3b9e4c2fd6a288c8bf3`。
用户授权继续完成待办并提交 PR，缺客体验收不阻止代码提交；未授权结果仍不得写成通过。
本记录不替换 `comprehensive_audit_20261112` 的冻结证据，也不修改 merger 专用 state 快照。

## 实装

- newlib 从源补丁修复原生 `_Atomic` 初始化和 tgmath 类型选择/单次求值，构建和 SDK
  导出时重新应用，未手改 vendored 生成头。源补丁纳入构建指纹。
- CPython 时间桥使用 sys46/sys47，sleep 释放 GIL并传播错误；真实桥宿主回归和线程 fixture。
- 31 个旧图形 runner 启动 Interactium 与 Display，两进程在基线/服务死亡场景完整回收。
  双窗口 fixture 检查并存、独立销毁和两个 input worker join。旧错误文本、像素游标、
  input 日志格式、Display 独占探针和 GPU 全帧合成预期一起迁移。
- QPA expose 改用窗口本地坐标；隐藏未聚焦窗口不清另一窗口焦点。Display 增加独立
  `fault-present` 注入，保留旧 `fault` 的首次请求行为。
- 原始编译与对象字节来源捕获接入 newlib/GCC/Qt/双 SDK，发布身份与 license audit
  校验归档覆盖；导入保留原始 id，legacy 预编译 newlib 单列。
- 固定工具链 export/restore 和串行 candidate 入口；候选构建明确回执选择、失败停止、
  未验收状态。release 流水线拒绝覆盖冻结目录。
- P4A runner/exporter 使用真实 install ISO 和新报告名；file_client 叠加改为同名
  替换，旧来源资格明确失效，不能把混合 SDK 当作重新资格化。

## 本记录检查

实际通过：归档读取 14 项、来源捕获 2 项、newlib cache 3 项、release SDK binding
11 项、libc symbol audit 1 项；真实 newlib 头 C 编译/运行；CPython 时间桥 C++ 编译/运行；
Display 与 supervisor 两单元按仓库严格 flags 宿主编译；Python 语法、P4A naming、diff。
Qt/CMake 集成检查因宿主缺 cmake 未运行。候选构建实跑在 NASM 缺失处失败，未复制旧产物。
各运行库、Qt、GCC/newlib 固定目标构建、实际设备、SSG stress、发行烟测均未运行。

后续 VM/CPU、文件身份、IPC/device/network 与原生 SL3/SL4 使用独立工作记录；总报告
在合并这些实现后汇总。Pillow 历史 fault 和 SSG D13/D14 不能仅凭上述修改宣告解决。

## 最终集成补充

- 最新上游 IP4 与普通 COW 组合时，活动 bulk 映射 fork 会破坏 grant 共享/撤销假设；
  已在实际 fork 入口返回 busy。设备映射采用同一前置限制，仅持 handle 不阻断。
- grant close 原先逐映射独立 can_unmap，无法预见前一拆分消耗最后 fragment 槽；
  改为对每 holder 按真实顺序整体预演。4 KiB scratch 放全局，受既有 syscall gate
  串行化，不占线程 4 KiB 栈。实际 helper/reservations 与 fork 入口 8 场景在
  eager/COW 两配置通过；真实 sys112 query 跨页 COW/OOM/父子隔离回归通过。
- 构建交叉审查复现并修复 `/dev/null` 成功编译探针被来源 wrapper 拒绝，以及 tar
  data filter 改权限导致自身工具链归档无法恢复。来源捕获回归增至 3 项，真实 tar
  恢复回归 1 项，均通过；固定工具版本检查在该 tar 单测中明确替代，不冒充已安装。
- 进一步真实编译和 nm 检查发现：修复 tgmath 后 long double complex sqrt 引用
  `csqrtl`，当前入库 libc/libm 没有定义。头类型问题已修，预编译数值库覆盖不足仍
  未完成，详见后续总报告；没有用宿主数学库证明目标 archive 已完整。
- 合并后的 K03 ABI-only 宿主夹具因新增 copyout 入口首次编译失败，补上该夹具的
  普通宿主内存边界 hook 后 9 项通过；真实 COW 行为由独立真实页表回归覆盖。
  原失败输出与修复后输出都保留在总报告中。

## 图形 runner 最后交叉审查

- 修正 `qt6_gui_acceptance.py` 像素分支：实际 VBE 日志只有 width/height/stride、
  physical/bytes，没有 format 字段；原迁移正则必然得不到匹配。现在读取真实三字段，
  按 `display.cpp::init_vbe` 已强制的 XRGB8888 契约解码 BGRX，不新增内核日志接口。
- 首条 present 故障现在明确属于 **compositor 首次合成提交**。Interactium 的
  create_window 就会产生 damage，因此故障可能发生在 QPA 创建窗口回包期间，
  也可能由之后的 frame/input 路径观察。两个 runner 共用严格分类：只有
  create-window failed + exited code=1，或 frame commit failed/disconnected +
  exited code=72 才接受，并同时要求实际 `fault_after_present` 标记、Display fault
  回收、compositor 11/13 退出回收和完整资源基线恢复；任意其他非零退出不算通过。
  code=1 依据仓库实际 newlib `abort` 对象反汇编的 `raise(6); _exit(1)`，以及
  本地 `_kill`/`_exit` 桥；Qt 的 qFatal 默认 abort 行为见
  <https://doc.qt.io/qt-6/qtlogging.html#qFatal>。没有改变注入 ABI 或生产 QPA 行为。
- 本轮仅检查 Python 语法及上述解析器的有限正反例，**Qt 固定版本目标链接、当前
  threaded newlib/Qt 实际退出链和全部图形 guest 均 NOT_RUN**。允许集合是待匹配
  SDK 重跑的严格条件，不是这两个客体结果已经发生的证据。既有持续运行客户端的
  service-death 用例继续独立保留，不将首次合成故障当作已覆盖客户端帧提交故障。

Aurora render 回执也移除旧 `ns/gui_ns` 正则，明确输入端到端 latency 为
`not_measured_current_protocol_has_no_source_timestamp`，保留实际按键事件计数。
没有从缺失时间戳的当前协议推导延迟，帧提交与 widget update 已有时间观测仍单独记录。
