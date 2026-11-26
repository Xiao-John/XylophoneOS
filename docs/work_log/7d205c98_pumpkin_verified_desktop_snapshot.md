# 7d205c98 · 消除受验证 Mobius 启动中的重复读取

以本地 `4706cc77` 和 Pumpkin 活动吊销分支 `8ddafe53` 为基线。旧路径先读完整已固定 ELF
计算摘要，再到文件服务读取约 24.7 MB 的 LOAD/TLS 内容以建立映射。旧镜像
`f2d901b42f4bb8c1` 的一次正式启动在 140 秒内持续全黑。其间客体仍运行，显示服务、客户端
与焦点已就绪，单个现场样本落在 ATA 读取。独立成功采样也显示，桌面任务已分配后文件服务
仍继续读取，且真实首帧在该阶段之后到达。

保留同一只读 pin 和精确的长度校验，在可用页满足子进程预算时把文件读入监督器私有 RW+NX
映射，同时计算 SHA-256。只有摘要匹配后才从这份已验证内容映射子进程。关闭 pin 并完成
快照回收后才能启动子进程。内存不足时沿用原有固定文件流式读取。提交和撤映射均采用
VM continuation 支持的 4096 页批次。中间镜像 `c1c9938521a53190` 实际分配了快照，
但撤映射超过单次操作容量，候选在首帧前拒绝启动。
[加载器约定](../e04_loader_sdk.md)

用同一 32,670,232 字节 glibc Mobius ELF 执行两次独立的管理模式无吊销观测。在 QEMU
11.1.2 的本机样本中，首个管理询问从 26.421 秒提前到 17.609 秒，相同 Midnight 首帧
从 28.422 秒提前到 20.367 秒。修复镜像 `7dce547d94f7222f` 的监督器已提交用户页从 102 到
8079，再于首帧前恢复到 102。Ctrl+Q 后客体确认正常注销，QEMU 退出码为 0。两次采样
用于定位启动阶段，样本数量不足以估计首帧时延分布。历史记录中首次周期身份检查不回应的
早退仍缺少因果证据，继续独立追踪。

```sh
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 scripts/build.py --output-dir "$SYSTEM" \
  --pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login \
  --pumpkin-mobius-elf "$MOBIUS_ELF"
python3 -B tests/pumpkin_mobius_guest.py --system "$SYSTEM" --executable "$MOBIUS_ELF" --output "$OUTPUT"
XOS_LWIP_SOURCE_ARCHIVE="$LWIP_ARCHIVE" python3 scripts/build.py --output-dir "$LEGACY_SYSTEM" \
  --pumpkin-anchored-probe --pumpkin-native-login --pumpkin-user-login
python3 -B tests/pumpkin_user_login_guest.py --system "$LEGACY_SYSTEM" --output "$LEGACY_OUTPUT"
python3 tests/abi_doc_consistency.py
```

同一源码的正式客体验收通过 8 项。普通打开显示真实 Midnight 和 Daybreak，退出后同一
凭据可继续认证。管理模式等待但不发送吊销信号，Ctrl+Q 后 874 毫秒确认注销和资源
回收。活动吊销在 3282 毫秒后确认持有者拒绝和完整回收，更改同尺寸 ELF 的启动继续
被拒绝。独立无桌面镜像 `1e85a6e85906dd85` 通过 13 项原登录回归，ABI 文档对照通过。
[镜像、SDK、基线失败和客体验收回执](../reports/pumpkin_verified_mobius_snapshot_20261126/manifest.json)

## 与 Qt Quick #292 组合验收

将 `31dae7e2` 合入得到 `05c11d52`。与上轮镜像的输入清单相比，变化仅为 Qt Quick 外部
套件的两个构建脚本及其验收脚本。两个配置的 33 个内置客体 ELF 分别与上一轮逐字节一致。
Mobius 沿用已绑定 glibc SDK 和应用配置的 ELF，并核实了文件 SHA-256、系统清单和实际
客体回执的绑定。组合源码分别重建桌面镜像 `d33867f68e9733c3` 与无桌面镜像
`494c64a6aeddd778`，独占运行 QEMU 并通过 8 项桌面、13 项无桌面和 ABI 对照。
管理模式无信号时，Ctrl+Q 后 814 毫秒确认注销及资源回收。活动吊销在 2560 毫秒后确认
原会话拒绝及资源回收。历史失败和早期身份复核原因未明的记录继续保留。
[组合源码与真实客体回执](../reports/pumpkin_verified_mobius_post292_20261126/manifest.json)
