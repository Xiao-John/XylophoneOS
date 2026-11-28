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

## 已实际通过的隔离生命周期与 HTTPS 子集

以下新证据在恢复后的已发布 Linux SDK 开发环境重新产生，位于
[`p1f_clarke_20261128`](../reports/p1f_clarke_20261128/manifest.json)。这是进行中的
部分验收，不把启动失败 probe 或独立 HTTPS probe 算作 WebCore/Qt 整页通过。

启动/abort 客体使用隔离的 `XOS_LOADER_TEST_BAD_START_ENTRY=1` 镜像。20 个实际
post-prepare start 拒绝均记录 never-started=1、abort-attempted=1、kernel abort=0，
然后由可信控制器回收撤销记录，policy occupancy 每轮从 0 回到 0。double-abort
负例记录 callback 首次 abort=0、loader 第二次 abort=-1；没有推定回收，policy
occupancy 保留为 1。子程序执行标记始终未出现。服务退出后资源恢复为
`[free_pages=129677, tasks=3, completions=1]`，与已初始化基线完全一致。

第一次验收曾在最终页数比较失败一页。独立的无 ClarkE `net-start/net-stop` 周期
重现相同差异；`pci.cpp::observe_supported_reset` 首次为 PCI instance 建立内核
整个启动周期保留的 reset-status 观察映射。第二个普通周期没有新增页。更新后的
runner 单独记录 cold `[129678,3,1]` → initialized `[129677,3,1]`，必须第二周期
严格相等，再开始上述全部 21 个故障用例；没有修改生产实现或放宽进程回收断言。
两份失败/通过原始 serial 与独立 device isolation 记录均保留，且绑定 PCI/paging
源码摘要。该例的 ISO SHA-256 为
`d132e8334b66136d7b49479c848c20096e225fc56e0508353cea9b279e6b43bc`，
native manifest 为 `1ad679a0a3926de8b2d862aca78c4732c0110b791fb1dcfdc4cacf7964c42c9b`。

HTTPS 实测还发现共享 HTTP reader 的原有入口要求 EOF，不能在 body 完成后主动
发起 TLS 关闭。因此保留原 `read_framed_response` 行为，并新增准确 Content-Length
边界入口；它仅交出暂存响应，ClarkE 必须再完成真实双向 TLS 关闭才能返回成功。
第一次等待 EOF 而超时的 serial 也保留，最终真实 guest 验证如下：

| 场景 | 实际结果 |
| --- | --- |
| client-first 正常关闭 | TLS 1.3、200、32 字节 nonce、双向 close_notify，约 1.36 秒 |
| server-first 正常关闭 | TLS 1.3、200、32 字节 nonce，约 1.13 秒 |
| 对端不回关闭通知 | 原总 deadline 到 3.00 秒，timeout -205，response 清空 |
| 裸 TCP EOF、额外 application byte | IO -207，response 清空 |
| 错误主机名、未知 CA、过期证书 | denied -202，握手 alert；没有 HTTP application request |
| 负例后再次正常请求 | 成功、32 字节 nonce、双向 close_notify |

每轮资源回到 `[129506,4,2]`，最终服务退出回到 `[129677,3,1]`。实际 guest report
SHA-256 为 `1609957ca0bccc534f8a4647d6676d3e513bbc040b074bc0f1c6e8bb08909867`，
probe ELF 为 `b46bbe9381e6d73e6809a84b7b190fda54a85d4cd94f93aa0b80b06a8ce05d22`。
测试使用显式受控 origin/CA，不宣称公共 CA、DNS 或任意互联网资格。

net2 host 回归实际通过 33 个 real-lwIP core 场景、2 个生产 loop 场景和客户端畸形
policy 响应检查。HTTP reader 在 SDK `/usr/bin/g++` 的 ASan/UBSan 下通过 fragment、
旧 EOF 语义、精确 body、截断、surplus、重复/不支持 framing 检查；该受跟踪 SDK
环境设置 `ASAN_OPTIONS=detect_leaks=0`，不宣称 LeakSanitizer 资格。

可复现的本轮命令以各自独立输出目录执行，已有目录保留而不覆盖：

```sh
python3 tests/net_service_host.py --archive "$LWIP_ARCHIVE" --output "$NET_HOST_OUTPUT"
python3 tests/net_client_host.py
CXX=/usr/bin/g++ ASAN_OPTIONS=detect_leaks=0 python3 tests/browser_http_framing_test.py --output "$FRAMING_OUTPUT"
python3 tests/clarke_https_guest.py prepare --certificates "$TLS_FIXTURES"
python3 tests/build_clarke_https_probe.py --sdk-build "$CXX_SDK" --sdk-profile "$SDK_PROFILE" \
  --openssl "$OPENSSL_TARGET" --tls-root-der "$TLS_FIXTURES/clarke-root.der" \
  --tls-origin https://tls.xos.test:9443 --tls-address 10.0.2.2 --output "$HTTPS_PROBE"
XOS_QMP_TRANSPORT=pipe python3 tests/clarke_launch_guest.py --system "$LAUNCH_SYSTEM" \
  --probe "$LAUNCH_CHILD_STRIPPED" --output "$LAUNCH_GUEST_OUTPUT"
XOS_QMP_TRANSPORT=pipe python3 tests/clarke_https_guest.py test --system "$LAUNCH_SYSTEM" \
  --probe "$HTTPS_PROBE" --certificates "$TLS_FIXTURES" --output "$HTTPS_GUEST_OUTPUT"
```

ICU、FreeType/HarfBuzz、libxml2、Fontconfig 已实际重建完成；Skia 软件绘图归档仍在
编译。WebCore 全页 ELF、Qt 视口、超过 16 次真实浏览器导航和 renderer trap 恢复
仍待执行。为避免 UI 的 close 消息与其 pair 回收竞争，应用协议的既有 `close`
操作增加明确反向 ACK，GUI 最多等待三秒；该完整 UI 路径也仍待真实客体验证。

## 临时对象构建与后续输入

共享磁盘空间不足时，完整 WebCore builder 可显式指定 `--temporary-objects`，
只把 CMake target 对象目录放入本次 SDK 会话的私有临时盘。此模式关闭 thin
archives；真实普通归档、生成头文件、编译命令和日志仍留在输出目录。完成真正
链接后，逐对象记录尺寸与 SHA-256，保留非对象辅助文件，再清除可重建的临时
对象。失败时保持同一个 SDK shell，才能继续 `--resume`；不能把失效的临时
路径当作可复用产物。

该选择先用 Skia x86-64 对象实测。第一次自动选取的最小对象是本架构上为空的
LASX 单元，只证明归档文件格式，不证明实际代码保存；原结果保留。第二次明确
使用非空的 `SkPoint.cpp` 目标对象，通过临时目录生成 `!<arch>` 普通归档，删除
原对象后，再以目标 `ld -r --whole-archive` 成功链接。其 906 字节执行节逐节
保持完全相同，公开投影标明原始报告摘要与省略的宿主路径。完整 WebCore
临时对象构建尚未完成，不把此小验证算作 WebCore 链接通过。已完成的字体、XML
和 Fontconfig 源码/对象按前后哈希清理；最终库、头、probe、manifest、许可证、
日志和锁定源档均保留。

QPA 补上 F1–F12 的扫描码映射，浏览器 reload runner 才能真正用 F5 触发导航。
最终 GUI 客体须合入 P1-G 的真实 Interactium 服务；其 wire v1 保持不变，F 的
Ctrl+Q/ACK/正常退出通过既有 `destroy_window` 回收窗口，不声称覆盖 G 的
独立 `close_request` 请求路径。

Skia、Fontconfig backend、WebP 和 SQLite 现均实际完成。Skia manifest 为
`6b84f3cf153107391e842abc8058615ae460e2499a84a56264818932b538966b`，
backend manifest 为
`8e0eb1207b69e9dfc406b8209a7bb55a0d9533c71c8a1974c6e5e8a06327b8f9`。
新的 backend 在冻结原生镜像中运行了真实文件/字体/绘图客体：DejaVu Sans 的
λ 字形编号为 848，绘得 107 个非白像素并退出 0；空字体目录按预期退出 5。
两次均恢复为 `[129678,3,1]`。完整原始报告和 serial 已进入同一平铺证据目录，
这仍是依赖子集资格，不替代 WebCore 或 Qt 的最终客体。

恢复检查点 4 为 `b0b426d51340348f8a3ec1e6c0ea1b4406033508`，tree 为
`93ce71c2cc3ecfeca78567b83c73c7f576eaba99`；其后修改包括上述非空归档验证、
临时对象生命周期、失败尝试日志保留、WebCore 源/生成树的前后绑定和 QPA 键盘
入口。WebCore 完整配置现已成功并进入实际 bmalloc、WTF 和原生 LLInt 编译。
当前完整页面链接、六类 DOM/CSS、Qt scanout 和全部浏览器生命周期仍未完成。

检查点 5 为 `ca093c9d1a5634cad46c6a088a06a7098faf3890`，tree 为
`3545ae1028c2b18a41e57a5da0171d2a3a075a93`。随后给 diagnostics 导航输出增加
UI 自身预算的实际查询结果、pages 和 threads，runner 将保留它与全局 free-pages
的两份顺序快照。每轮已有 worker tasks/completions 与 policy 归零检查，最终
退出才检查全局页数精确恢复；当前没有用固定页数猜测 Qt 的存活缓存，也没有把
待跑的逐导航采样当作稳定性通过。真实数据若显示持续增长，必须定位处理。

浏览器 runner 补充两条仍待实际运行的路径：等 renderer 真正完成 WebCore paint
后按 Esc，以及在同一阶段用下一次导航替换。诊断只打印实际阶段，不引入等待或
合成画面；runner 要求内核 wait 的 killed outcome、没有完整 frame ACK，并检查
取消后的实际 scanout 仍等于上一个已确认页面。原请求仍在 broker 中时的取消
保留为独立用例。完整正常集合因此扩展至 29 次导航。

最终整合采用原应用 producer 与新原生镜像分别绑定的方式。当前只读核对到主线
`a4d409695c4368a8522a15cb8565fd5905064d72`：process ABI 新增可选 pipe 查询，
G 保持 Interactium wire v1，C 的动态 capsule v3 不参与 ClarkE 静态 ELF 启动。
新 `--system-source-root` 对传入原生 manifest 的 boot/kernel/shared/user 和
ClarkE 控制器所用头文件逐一核验；旧 WebCore/Qt/SDK 的摘要不修改。该兼容判断
仍须以最终整合镜像上的真实 DOM/Qt/浏览器客体证明。

独立检查发现 QPA `exchange` 原先仅核对 IPC transport 的最大 payload，未核对
调用者更小的回复缓冲区。现在五个调用都显式传入容量，共用 production decoder
先核对实际收到的长度、请求对应回复类型和精确 payload 尺寸，再复制并发布输出。
失败保持调用者的输出不变，不改变 Interactium wire 协议。该修复由本轮 C 线
协作者实现，保留本线已有 frame receipt 与键盘映射。

在发布 SDK 中用 GCC 16.2.0 实测普通和 ASan/UBSan 各 32 例通过：五种合法消息
由真实 Interactium dispatcher/service 生成，随后覆盖小 heap/stack 目标、超长、
截断、错误类型、序列、session 和版本。LSan 在该执行环境关闭，没有泄漏检测
资格。原始报告 SHA-256 为
`9810a5cd12feb9dd42328b8986dec09468772489bd5dcd00bd57e98cd19c907d`；
公开投影和两份逐例日志进入平铺证据目录。该门没有编译整个 Qt 插件或运行客体。

另一次已完成依赖清理前，实际检查活 WebCore 的 `compile_commands.json`、
`CMakeCache.txt` 与 Ninja 图，确认没有 include/link 路径引用待删目录。只删除
本线已完成的 ICU、raster、font-backend、WebP、SQLite 可重建源码和中间对象，
467 个保留项的原始字节前后相同，全部锁源档复核通过；删除 283,621,803 逻辑
字节。最终 prefixes、归档、probe、许可证、原始日志与每个被删文件的摘要均
保留，没有改动活 WebCore 源码、生成文件、SDK 或另一条工作线。
