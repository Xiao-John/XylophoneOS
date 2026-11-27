# e48a6d31 · 原生动态 identity 与 generation 准入组件

本模块把 D0 的 native identity 和 generation 声明落实为有界元数据编码、
SDK decoder 及受信单线程启动者内的候选状态。**公开 spawn/exec 仍拒绝动态
ELF**；此 PR 不关闭整个 D3/D4，也不改变 glibc 默认发行资格。

## 接口与实际行为

共享头 `xos/dynamic_abi.hpp` 固定 128 字节 identity、128 字节 generation
header、512 字节 object，最多 12 对象、4 个预先批准的 generation 根。
`xos/dynamic.hpp` 与 native `libxos_loader.a` 导出 decoder 和 catalog。
字段、预算、版本/兼容、错误与信任来源见
[dynamic_admission_v1](../contracts/dynamic_admission_v1.md)；ABI 登记和 SDK
文档同步，无新 syscall、startup 保留位复用或 newlib 私有耦合。

ELF note 必须唯一、完整、与批准身份逐字节相等且处于实际只读 LOAD 中；
拒绝可写虚拟别名、外来 OSABI、错误对象角色、无身份/重复身份、错误或别名
PT_INTERP、未知版本与越界结构。完整对象 SHA-256 与长度由 generation
外部记录绑定，避免嵌入对象自身产生循环摘要。

generation decoder 在同一有界私有快照上核 SHA、ID、SDK 和结构。图保留
依赖顺序，拒绝重复对象/路径/SONAME、缺边、自环/循环、不可达库、映射重叠、
超预算和非法路径。`activation_catalog` 复制批准根；显式 activate/rollback
使用 sequence 防止过时更新，revoke 会令该根此前 capture 的 admission 也
失败。切换 active 本身不重新绑定已有 capture；所有成功变更增加 sequence。

这不是持久激活控制器：候选根须由受信系统镜像/独立认证控制器提供，catalog
不接受任意磁盘 policy 作为信任根；ticket 不是外部 capability；跨线程同步、
重启后撤销/防回滚、签名发行政策仍待实现。组件也不凭 manifest 的声明图
断言真实 ELF 的 DT_NEEDED、SONAME、符号版本和重定位已验证。

`verify_object` 的 reader 必须保持同一 readonly pin 或不可变私有副本。
公开 loader 后续解析、复制和映射仍须使用这个相同实例；前后各算一次可写
路径摘要不满足要求。本模块不在父方执行对象代码，也不以 decoder 成功宣称
constructor/main 已运行。

## Pre-release SDK 中的实际验收

开发环境是 SDK Preview 2 Linux x86-64，归档 SHA-256
`60df6913fe2a56517e645c93673ebd9590ba3dd90acc56030c80c3738955cac9`。
新系统/native SDK build_id 为 `f4bc8047111f47ab`。验证器从该 SDK 的
`libxos_loader.a` 链接实现，未以测试专用复制实现代替已导出 archive。

```sh
xos-sdk --workdir "$SOURCE" sh -c \
  'PYTHONPATH=scripts python3 tests/dynamic_admission_guest.py \
   --system build/p0_dynamic_admission_system --output build/NEW_ADMISSION_REPORT'
```

| 检查 | 实际结果 |
|---|---|
| 同组 identity/generation/catalog 宿主案例 | 39/39 通过，严格编译警告为错误 |
| 真实 QEMU 客体 | 40/40 通过，含实际 GCC 链接 note 文件的 readonly pin/定位读取/游标不变 |
| 资源回收 | 前后均 `[129709, 3, 1]`，正常退出 0 |
| ABI 文档一致性 | 通过，无编号变更 |
| docs_consistency 全局历史溯源门 | 补取 shallow clone 缺失的历史 Git 对象后通过：2,130 条链接、78 项 syscall、73 条历史来源；早期失败原样保留 |

负例覆盖实际 note 缺失/篡改/重复/可写、外来 ELF、PHDR 预算、短文件、对象
摘要与工具 ABI 错配；generation 摘要/ID/SDK 错配、路径、解释器别名、SONAME
歧义、图/映射/时间预算；过时激活、已批准回滚、撤销取消旧 capture、拒绝撤销
后的回滚、候选根不可重初始化和错误 ticket。manifest 的算法测试采用声明
工件；它不是一组已经发行的 glibc 动态应用。

第一次严格编译暴露三个显式窄化转换，已修正。首次客体实际 39 项通过且退出
0，但 harness 误把部分字符串当作完整结果行，整体报告如实保留失败；修正
为完整行后，再新增解释器别名负例，并对新 SDK 重新构建验收。最终 40 项
回执没有用旧日志改写。公开
[证据索引](../reports/dynamic_admission_20261127/manifest.json)保存原始摘要、
路径脱敏/换行处理说明、最终日志和早期失败。
公开路径检查为 `PUBLIC_READY`；唯一 `DOUBTFUL` 是负例中故意提供的客体
`/tmp/ld.so.1` 解释器别名，已人工核对，不是宿主路径。

## 继续实施的 P0

下一公开启动模块必须将实际 ELF 图/符号/版本与封存 generation 核对，完成
同一 pins 的父子交接与不可逆提交前的撤销检查，再通过内核认证 peer/controller
的 ready/error 和统一绝对期限封闭成功/失败语义。公开 exec 必须区分提交前
保留旧映像和提交后终止，不能用 spawn+wait 代替。同一完整候选还需正式
D4 多应用和 SDK/发行回退组合。本组件的通过不能替代这些门。

## 历史对象补取后的复验

原 `docs_consistency.log` 的失败来自 shallow clone 未持有 `source_index.json`
指定的历史 commit 对象，不是该 commit 实际缺少原文。补取既定
`a265061ee00b787287011e5939054ebe3da4e397` 后，在本模块独立来源树复跑
`tests/docs_consistency.py`，全部通过。未修改历史文件、来源索引或测试条件；
[补取后报告](../reports/dynamic_admission_20261127/docs_provenance_restored.json)
与原失败同时保留。该复验不改变 guest、SDK archive 和生产源码资格。
