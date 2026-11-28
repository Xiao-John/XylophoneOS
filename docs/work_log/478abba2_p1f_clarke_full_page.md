# P1-F ClarkE 全页集成恢复记录（进行中）

## 范围与交付门

本线实现 `docs/plans/p0_completion.md` 的 P1-F：真实 WebCore 页面解析、DOM/CSS
布局与软件绘制、Qt 视口、独立 renderer/network 进程，以及导航、取消、故障后的
资源回收。静态归档、tokenizer、liteHTML 或伪造平台成功值均不构成此项验收。
恢复基线为 `6332527ab64e92371266363f41f3247717a3cac8`，包含 P1-B 进程树预算与
P1-E 主线变更。本记录的进行中快照用于保存可审查源码，不代表 P1-F 完成。

## 环境中断与证据边界

2026-11-28 执行环境断开后恢复到了较早磁盘快照。本线工作树、未发布的 SDK、
依赖前缀、WebCore 对象及运行日志均未出现在恢复的磁盘中。恢复前对话中记载过
构建进度和测试结果，但其原始产物、日志与 manifest 不在当前证据集中；不能将
这些摘要当作本次可复核资格。本线从远程主线重建，逐步保存明确标注为进行中的
远程源码检查点，再重新生成构建与客体证据。

## 本快照已恢复的实现

- `src/ports/webkit/target_inputs.py` 验证依赖的完整 artifact 清单、SDK tree、
  头文件覆盖、规范路径与别名目标；仅允许 ICU 已独立记录的前缀内元数据别名。
- ICU 构建记录全部已安装文件与头文件，记录实际 SDK/profile 摘要。
- 字体构建可显式消费同一 SDK 重建的 ICU；旧 ICU archive 入口仍要求旧版完整
  SDK 绑定，不能悄悄把历史资格转到新 SDK。
- libxml2、Skia、Fontconfig 的重建链绑定当前完整 SDK 与实际依赖清单，不再
  把历史报告的哈希作为唯一可构建前缀。
- SQLite 构建使用既有 Files VFS、真实 pthread mutex、单 renderer 进程的
  exclusive rollback journal 范围，关闭 WAL 与动态扩展。未宣称跨进程数据库锁。
- 源码下载器只读取既有锁中的来源与摘要，不升级依赖；签名验证仍由各端口准备
  工具执行，下载完成不等于构建或客体合格。

## 已重新执行的检查

恢复后的普通宿主 Python 执行：

```sh
python3 tests/test_webkit_target_inputs.py
python3 -m py_compile src/ports/webkit/target_inputs.py \
  src/ports/webkit/page/build_sqlite.py src/ports/webkit/icu/build_target.py \
  src/ports/webkit/fonts/build_target.py src/ports/webkit/libxml2/build_target.py \
  src/ports/webkit/fontconfig/build_target.py src/ports/webkit/raster/build_target.py
```

8 个依赖绑定负向/正向用例通过；Python 语法检查通过。该结果只验证宿主配方的
输入边界，不代表 XOS SDK、WebCore、Qt 或网络客体通过。

## 当前未验项与继续顺序

1. 在已发布 preview-3 Linux SDK 中重新生成唯一静态 glibc C/C++ SDK，并交由
   P1-D 只读消费；动态 GNU runtime/bootstrap 由 P1-D 在 C 接口冻结后另建。
2. 重建全部锁定依赖和真实 WebCore full-page ELF，补齐实际链接所需平台实现。
3. 完成固定 ELF 安装绑定、Xsh prestart 预算与 net2 撤销、子进程自有 IPC pair、
   Qt backing-store flush ACK 与明确的 navigation/cancel/failure 清理。
4. 运行 DOM/CSS 几何与像素、真实 Qt scanout、HTTP/受控 HTTPS、原始 net2 拒绝、
   越权 release、超过 16 次导航、renderer fault 与实际 start/abort 故障客体。
5. 保存平铺证据 manifest、实际暂存索引公开路径检查；完成后再提交可合并 PR。

全部全页、Qt 和生命周期客体验收在此快照中均为 **未运行**。

## 第二份恢复检查点

第二份源码恢复加入真实 WebCore page adapter、六类 DOM/CSS HTML 与几何/像素夹具、
独立 renderer、OpenSSL/net2 网络代理、Qt `QBackingStore` 视口、固定 ELF 安装绑定、
Xsh 可信会话控制和系统构建入口。该检查点尚未完成 C++ 编译或全页/Qt 客体运行。
Python 配方语法检查重新通过，既有 8 个依赖绑定测试重新通过。

net2 新扩展最终使用 operation **21**、独立 revision 1 请求与快照。主线
[#444](https://github.com/Xiao-John/XylophoneOS/pull/444) 已为另一条工作线登记
19/20，故本线没有复用它们；operation 21 的协调登记由
[#446](https://github.com/Xiao-John/XylophoneOS/pull/446) 合入。旧 capabilities
位和 revision 不变，控制器用 operation 21 query 发现能力，旧服务拒绝则不启动浏览器。
具体权限与回收规则见 [生命周期契约](../contracts/clarke_renderer_lifecycle.md)。

静态 loader 新入口输出独立的 version-1 abort outcome，不改变 `spawn_options`
布局和动态 hook。隔离测试编译分支在 prepare 之后把真实 start entry 设为零；
测试分别检查实际 start 失败/abort0，以及 callback 先 abort 后第二次 abort 失败时
保留撤销记录。恢复源码中已有该夹具与构建入口，实际 guest **未运行**。

恢复后的唯一静态 SDK 实际构建完成，身份核验结果为
`candidate_binding_verified`，guest 资格仍为 `not_run`：

| 输入 | SHA-256 |
| --- | --- |
| `build/p1f-c-sdk/manifest.json` | `92c8885e8c13b37ae5192a39890f34a7a755dab78334ecce0661fbb003aa89cc` |
| `build/p1f-cxx-sdk/manifest.json` | `0c876bac53354501159df75813711002c41baede650f1878116bb64a80a8190b` |
| `build/p1f-profile.json` | `736d3353d9aad14d019dbc678b77dbb8f6fe8585bed84b71e1f858566a7a3f9f` |
| C++ SDK tree | `ce808de26f1ede38a543c94bba5d5a5592606c71305267854cb57ea519429254` |

Profile id 为 `xos-x86_64-glibc-p1-20261128-v1`。C SDK 的 glibc 源码与 configure
目录先保留供动态 runtime 工作线协调；该线随后完成独立重建并确认不再消费这些
临时输入，本线才核验 1106 个保留文件并删除已完成的可重建 source/configure，
最终 sysroot 和 SDK manifest 前后不变。C++ 构建完成后核验全部
最终 artifacts，再清理仅本线可重建的 `work` 临时目录；前后 1987 个 sysroot 文件
摘要完全一致，SDK manifest 未改动。GNU 签名材料、源包对应性材料和全部构建日志
保留。该清理不触及其他工作区或已发布 SDK。

OpenSSL 3.5.9 已实际生成静态库和 probe ELF，报告状态为
`static_sdk_and_probe_linked`，其 guest 尚未运行：

| 产物 | SHA-256 |
| --- | --- |
| `build/p1f-openssl/report.json` | `2fe74a7144b9286a8fd3dd5f6f22b8fb33d52c7a8b6b9f835ec403de27d32266` |
| `prefix/usr/lib/libcrypto.a` | `a3dc4ba4d2da1f5c6b0f940c56ac901a6eb8c07bfdf03599802216b9bc1b5d96` |
| `prefix/usr/lib/libssl.a` | `c85f2cd53d5f122c2e26e4347351a3f6497edb0df59aa86ad4286585a1974e0b` |

ICU 按 jobs 2 重建，其他依赖、WebCore 完整链接与 Qt 构建继续。目前的成功项
是恢复源码、锁定输入和新的 SDK/OpenSSL 构建，不是 P1-F 的整页验收。

## 第三份恢复检查点的变更（验收待运行）

- QPA 保留实际 frame commit 返回值和每窗 serial。视口只有在同一 GUI 线程读取
  到新的成功 receipt 才发送 `presented`，避免把 Qt 的 void `flush` 当成成功结果。
- WebCore 使用 thin archive 控制磁盘峰值；构建记录逐个绑定真实 member 对象。
  后续链接仍重新核验完整对象闭包，归档生成本身没有全页验收资格。
- 仅 ClarkE bundle/隔离 launch-probe 配置的 supervisor 安装镜像使用 `--strip-all`；
  完整带符号 ELF 和构建来源保留，既有 128 KiB 镜像上限不变。此修复对应真实
  native 构建中镜像 131208 字节比 131072 上限多 136 字节的问题。
- 新增真实 guest runners：20 次真实 start 拒绝与 abort 回收、double-abort 保留；
  六类 WebCore DOM/CSS 几何和像素及错误颜色负例；独立生产 HTTPS fetcher 的
  受控 TLS 对端。当前检查点不把这些待运行 runner 当作通过证据。
- 按 [OpenSSL shutdown 契约](https://docs.openssl.org/master/man3/SSL_shutdown/)
  修正 blocking BIO 的双阶段关闭。首个零返回不是错误；第二次等待仍受原始
  deadline/call/byte 预算约束，未放宽 EOF、证书或主机名检查。
- net2 host fixtures 增加 query/release 的畸形响应、畸形请求、普通 peer 越权、
  满表失败、释放后容量恢复及 40 个 policy 生命周期；实际执行结果后续补录。

源码检查点仍不代表 WebCore full-page、Qt scanout 或任何新 guest 通过。
