# 6f637e1c P1-C 主线整合与冻结 GNU 运行时兼容验收

## 范围与结果

P1-C 冻结交付与主线合并后，定向 host 检查及两场真实 XOS guest 均通过。
这次验证的是原 GNU runtime/应用在新 native 系统上的兼容；原 23 场报告的
24 个文件逐字节保持不变，没有把旧运行时重标为包含新 K1 实现的产物。

| 身份 | 精确值 |
|---|---|
| main 第一 parent | 3cbb2f35bb4bdc4aabca6cff4e4fa56e74b5ac17 |
| C 第二 parent | dea4d6b0cbdee6cc696e15647e9a39100766b7fc |
| merge base | 6332527ab64e92371266363f41f3247717a3cac8 |
| 新 native 系统 build_id | 608aad6ff2fa8b5b |
| 新系统 manifest SHA-256 | 42ea150c37d8840e5ca42cc8e4bc63b16a7dc33d298c3e1a2c0ac3635275bceb |
| 冻结 GNU runtime manifest SHA-256 | a7a6360491bb8ebe13b85aab61be7d61d0cd26137d1f02f433d7ca908e8bd0dc |

本地执行 merge --no-commit --no-ff，没有创建 commit。远端发布由 root 以
上述两 parent 完成。本记录不修改 docs/state.md，也不提前声称 PR 已合并。

## 自动合并与语义检查

没有文本冲突。Git 自动合并了 docs/contracts/abi_registry.md 和
scripts/user_build.py。后者同时保留 G 的 Interactium 构建与 C 的 authority、
专用 launch fixture、有限 storage lease 和 PT_LOAD 校验。其余 24 个主线
生产源码文件与 27 个 C 生产源码文件分别与各自 parent 逐字节一致。

登记保留 G 多窗口、H pipe 状态及网络后续项、K1 已实现 sleep ticket、
K2 terminal/controller 与 K3 后续认领，以及 F peer policy 认领。
C 的 PCQ1、capsule v3 与 PPR12/13 按实际实现更新状态；D 的正式签名发行
控制器仍为独立交付。没有新增 syscall、扩大原 channel 配额或复用别人的编号。

具体源摘要、自动合并前后摘要和保留列表见
[source_compatibility.json](../reports/p1c_main_integration/source_compatibility.json)。

## 冻结运行时与当前主线的关系

当前主线相对旧 runtime 的输入清单有七项内容变化：

| 类型 | 内容变化 |
|---|---|
| native 输入 2 项 | process_abi.hpp、sdk.hpp 新增显式 pipe status 查询；旧使用方的布局和操作保持 |
| recipe 输入 1 项 | build_glibc_sdk.py 纳入 K1 sleep API |
| port 输入 4 项 | Makefile、Versions、clock_nanosleep.c、_Fork.c 纳入 K1 行为 |

新树另有三个新增 native 输入头和三个新增 port 文件，其中 sleep 公共／内部头
同时属于这两类。它们没有被倒填进旧 runtime 清单。三个 native ABI 身份头
dynamic_startup_abi.h、dynamic_abi.hpp、catalog_abi.hpp 保持原字节；用原 SDK
摘要重新计算得到同一个 native ABI：
9dafe8ee0e45fbc1ccb00ee2362d1be5db38584553efcb8ae7a50d699cd4c849。

两场 guest 消费原 C generation 201/202、原 bootstrap 和原 GNU libc/rtld，
每个输入与产物在运行前后核对。新系统自己的 native SDK 没有被冒称为旧 GNU
runtime 或旧应用 bootstrap 的生产者。新 K1 shared sleep API 没有在旧 libc
中被重新构建或验收；shared GNU fork 仍是原 ENOSYS 边界。

## 定向检查

| 检查 | 结果 |
|---|---|
| 生产 authority reader/admission | 18 项通过：9 普通、9 ASan/UBSan |
| 生产 closure/ELF | 46 项通过：23 普通、23 ASan/UBSan |
| 生产 provisioning store/codec/RPC | 普通与 ASan/UBSan 均通过 |
| 当前 ABI 速查 | 通过 |
| 生产 check_registry 的源码、保留段及登记校验 | 79 个 syscall 通过 |
| 实际 initial boot | revision 2；PCQ、完整闭包、GNU READY/ACK 与应用退出通过 |
| 实际三代 live revoke boot | 原 PID exec；GNU posix_spawn 父／子／孙；三代撤销前各成功启动，revision 3 撤销后各拒绝，最终退出 0 |

Host 检查编译生产源，但 authority/closure transport 是模型；真正 kernel peer
和 GNU 运行行为由后两场 guest 验证。ASan/UBSan 使用 detect_leaks=0，
没有声称 LeakSanitizer 通过。稀疏集成树未执行完整历史链接扫描；登记检查直接
调用原 tests/docs_consistency.py 的 check_registry，未把它写成完整文档检查。
结果与原始日志摘要见 [host.json](../reports/p1c_main_integration/host.json)。

构建和运行使用发布的 glibc preview-3 SDK 环境。新系统明确选择原来的有限
300 秒 launch acceptance storage lease，各 RPC 期限和普通 profile 保持。
命令使用以下路径参数，冻结产物的具体 SDK 和 generation 摘要沿用原 C 报告：

    python3 -B scripts/build.py --output-dir build/p1c-main-integration/system \
      --pumpkin-anchored-probe --pumpkin-provisioning-store \
      --pumpkin-catalog-fixture "$XOS_FROZEN_C_FIXTURE" --pumpkin-launch-storage-lease
    XOS_QMP_TRANSPORT=pipe python3 -B tests/pumpkin_catalog_integration_guest.py \
      --system-build build/p1c-main-integration/system \
      --program-build "$XOS_PROGRAM_201" --program-build "$XOS_PROGRAM_202" \
      --catalog-fixture "$XOS_FROZEN_C_FIXTURE" --runtime-build "$XOS_GNU_RUNTIME" \
      --output build/p1c-main-integration/guest

新系统的 2,327 项源码和 321 项产物运行后全部复核匹配，见
[system_build.json](../reports/p1c_main_integration/system_build.json)。
[guest.json](../reports/p1c_main_integration/guest.json) 保留本轮原始成功报告字节；
两个 boot 的原始日志摘要与转换方法见
[conversion.json](../reports/p1c_main_integration/conversion.json)。

## 资格边界与交付

这两场补充整合兼容资格，不重复原 23 场完整故障矩阵，也不替代原独立 Linux
UID provider 检查。旧 23 场及其原始字节仍见
[原 C 证据](../reports/p1c_catalog_authority/README.md)。新 guest 的 authority
是 developer backend；未声称物理宿主部署、任意物理掉电或 shared fork 通过。
没有为了整合而更改原 runtime、native SDK、程序或原始构建清单的状态。

独立 flat 目录为 docs/reports/p1c_main_integration。最终暂存文件由 public-path
门禁核对，flat manifest 核对所有派生文件；发布时保留上述真实源与结果边界。
