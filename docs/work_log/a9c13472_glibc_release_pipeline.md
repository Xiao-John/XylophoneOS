# a9c13472 · glibc 统一发行入口与显式冻结回退

基线 `daf2bd24`。本模块交付发行工具入口和实际文件事务，不关闭 glibc 最终
发行资格或动态链接 D3/D4。本次未修改内核、SDK ABI、默认已发布 release 或
`docs/state.md`。

## 问题与改动

工作区已有 `xos_sdk.py` 的双 SDK 绑定与独立盘回退，glibc 也有候选装配、
烟测和完整源/重链材料工具，但 `release_pipeline.sh` 的无参数阶段仍选择旧
newlib 目录。这会让不同阶段隐式选择不同运行库，最终资产需要人工跨目录收拢。

统一入口现默认要求 glibc 的实际候选和显式输出；旧流程经 `--newlib` 选择。
原显式 glibc package/smoke 和 application-preview 调用保持兼容。build 强制
普通和安装两组客体门，其他阶段复用现有生产校验器；缺输入不隐式回退。

freeze/checksums 要求基础 4 份归档、完整 v6 glibc/应用源与全部重链材料、同一
release 的包/GNU 烟测报告、仍可验证的 glibc 和冻结 newlib SDK 绑定。它核验
每份输入字节，在私有目录复制，再通过 Linux `renameat2(RENAME_NOREPLACE)`
原子提交一个完整目录。输入变化、缺件、错候选和同时出现的同名输出均失败；
不覆盖旧资产。回执移除本机 SDK 根路径，保留真实的 `passed_subset` 范围。
许可 gate 的显式构建必须与发行 system manifest 摘要一致。源码材料与客体报告
从同一有界字节快照解析并取摘要，该记录一直保留至冻结，避免校验后重取新摘要。

`rollback --state` 调用现有绑定工具选择 frozen newlib；恢复使用 `sdk use glibc`。
两条路径只改变选择文件，旧系统/工作盘仍依照现有独立盘契约使用。
[操作文档](../releases/glibc_pipeline.md)

## 实际验收

使用用户指定的 pre-release SDK Preview 2 Linux x86-64，归档 SHA-256
`60df6913fe2a56517e645c93673ebd9590ba3dd90acc56030c80c3738955cac9`。
在 SDK 的 Python 3.14.10（GCC 16.2.0）中运行；使用普通 launcher，不声称
网络 namespace 隔离。

```sh
xos-sdk --workdir "$REPOSITORY" python3 tests/glibc_release_pipeline_host.py
xos-sdk --workdir "$REPOSITORY" python3 tests/release_sdk_binding.py
```

新宿主 20 项和既有 SDK 绑定 11 项全部通过。新测试实际创建、校验、复制和
原子提交文件，验证输入改变/缺失清理、完整材料清单、报告错候选/错盘/profile
及失败状态拒绝、路径/校验和行注入拒绝、并发目的目录不覆盖、默认/历史命令
路由；注入校验期间和校验后更换报告、材料回执，以及许可构建错候选。另对 SDK 实际附带的 newlib sysroot 执行 glibc kit 检查并观察拒绝。
用于文件事务和报告绑定的合成输入明确标记为宿主 fixture，不记为真实 glibc
SDK、ELF、客体或发行通过。

[原始日志、环境和文件摘要](../reports/p0_glibc_release_pipeline_20261127/manifest.json)

## 尚待完成

本次环境仍在重建当前 glibc SDK，未具备同一最终候选的应用 kit、全部发行包、
GNU Seed、完整材料和旧版 SDK。完整 freeze 的最终候选输入、QEMU 发行烟测、
新旧系统冷启往返因此 **NOT_RUN**；已有历史回执没有改绑到本次代码。

默认命令入口切换已实现，最终默认发行仍需按
[glibc 默认发行验收表](../releases/glibc_default_gate.md) 提供完整组合证据。
公开动态启动、代际激活和 D4 多应用组合继续为独立实现任务；本模块没有通过
移除动态守卫、开放 dlfcn 或重命名固定闭包测试扩大运行时支持面。
