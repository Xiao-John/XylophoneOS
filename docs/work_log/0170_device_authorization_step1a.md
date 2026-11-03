# 0170 设备授权实施段 1a：ABI 面 + 分发骨架 + 负向探针

2026-11-01 · 分支 `codex/device_auth_step1a_20261101`。

## 1. 范围与产物

- 契约 §7 步骤①的第一段：`sys_device`(112) 端到端接通——
  `src/shared/include/xos/device_abi.hpp`（冻结面：12 错误值/11 操作/4 权利位/
  64 字节请求，static_assert）；`tasks.cpp` 内分发（快照→8字节对齐→范围→头校验，
  与既有 syscall 层同处匿名命名空间，复用 user_range_ok/copy_from_user）；
  已知操作 1a 诚实返回 `unknown`（过渡态，探针显式断言，1b 落地时必须改掉）。
- 注册表：112 claimed→allocated（逐项表 + 号段 112 allocated/113-127 reserved）。
- 客体探针 `tests/fixtures/device_abi_probe.cpp` + 跑手 `tests/device_abi_guest.py`：
  9 项断言（坏版本/坏尺寸/保留位/flags/未知操作/deadline 越权/未对齐/不可读输入/
  未实现 GRANT），真实镜像真实内核 PASSED。

## 2. 选择与原因

- 分发函数放 tasks.cpp 匿名命名空间（与 thread/display 同层）而非独立 TU：
  user_range_ok/copy_from_user/current 均为文件内符号，独立文件无法链接；
  单核非抢占系统调用内直接读用户内存的既有模式沿用（显示线同款注释语义）。
- 对齐校验补在探针实测暴露后（探针首跑抓到内核漏检 8 字节对齐——负向探针
  当场还债，这正是它存在的意义）。

## 3. 命令与证据

- `python3 scripts/build.py`（分支镜像 build/xos.img，含112）；
- `python3 tests/device_abi_guest.py --image build/xos.img --sdk <threading_sdk>` →
  PASSED（报告 build/device_abi_1a/report.json，serial 留档）。
- 探针过程修自身两 bug（汇编未约束 RSI/RDX=0、exit 标记前缀竞态）——过程见会话，
  最终探针是约束完备的。

## 4. 通过 / 失败 / 未运行

- 通过：客体探针 9/9；docs_consistency；abi_doc_consistency（allocated=67）。
- 未运行：grant/map/irq/dma 机制（1b-1e 未开工）；既有套件零回归未整套复跑
  （本段只加新分发路径，未触碰既有 case；整套回归留 1e 收口段）。

## 5. 下一步

- 段 1b：grant 表 + GRANT/QUERY/CLOSE/REVOKE（PCI 设备实例、代际 token、
  supervisor 授权路径），探针替换 unknown 断言。
- 不能误认成已实现：112 存在但无任何操作可成功；A1 三驱动仍在内核。
