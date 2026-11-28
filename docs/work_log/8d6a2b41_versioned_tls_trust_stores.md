# P0-N4 有界、独立固定身份的 TLS 信任库

本轮基于 `daf2bd24ce92525ce61054ebe585ab0e88ed06e4`，使用已核验的
XOS SDK Preview 2 Linux x86-64 常规 launcher。运行记录按 UTC 2026-11-27
存档。本模块不依赖其他 P0 PR，也不修改内核 ABI 或已冻结的旧报告。

## 改动与信任边界

原 native TLS 入口只接受单个嵌入 DER 根。本轮增加用户态 `trust_store`，
允许 1–256 个 CA、单项至多 16 KiB、总量至多 1 MiB。格式有显式版本、代际、
完整 SHA-256 和保留位；所有证书完整解析、CA/signing 用途检查、去重与界限
检查成功后才发布对象。`load_file` 有界读取，失败不留下半个可用信任库。

调用者必须从可信构建或独立认证的部署配置提供 generation/digest；目录中
旁置 receipt、网络/DNS 返回内容和文件自己声明的版本都不产生信任。加载后
不可变，更新用新对象；连接复制选中的根，既有连接不会因换文件偷偷改变信任。
显式回滚需要重新授权旧 pin，撤销已建立的连接仍须调用者主动关闭。

`stream::connect` 增加 store 重载，保留 hostname/SNI、真实时间、证书链与
TLS close_notify 验证。`browser_http::https_route` 可选择同一 store；ClarkE
构建清单同步新实现。原单 DER 入口保持，但完整 Qt 消费者未在本模块重跑。

新增 packer 不下载、不自动选择信任。它校验调用者指定的 PEM 摘要，调用真实
OpenSSL 检查 CA/用途/精确 canonical DER，按摘要排序得到确定性输出。临时
文件写完并 fsync 后用 exclusive hard link 发布，不能覆盖现有文件或 symlink。
这不是磁盘断电事务或多文件可信部署承诺。

## 实际构建与验收

预览 SDK 包 SHA-256：
`60df6913fe2a56517e645c93673ebd9590ba3dd90acc56030c80c3738955cac9`。
单独从已验签 glibc 2.44 构建的静态 SDK manifest SHA-256：
`c1df8e02985df4e37198885a4a8fc78f21344011b1b851e8be4524cefe13ab1a`。
Mbed TLS 4.1.1 和 lwIP 2.2.1 使用仓库原 source lock，没有升级依赖。
预览包缺 CMake；补用官方 4.2.0 Linux 二进制，下载包与官方 SHA-256 清单一致，
实际 cmake 可执行件身份保存在 probe receipt。

最终系统 build ID `2ef59f282e0e110c`，ISO SHA-256：
`1e54eb5d7436e8ca215164ed5f393cdb4f92363202b6c2caa0e447f55604e92d`。

| 检查 | 实际结果 |
| --- | --- |
| 主机 PEM 编译与发布 | 24 项通过；真实 OpenSSL，不用假的证书解析器 |
| 客体 trust parser | 15 项通过，含畸形头/DER、重复、尾随、长度、代际、leaf 不能充当根 |
| 完整客体序列 | 20 项通过，含原 TLS 回归、多根、更新、移除、授权回滚与缺熵启动 |
| 两个独立受信根 | 均成功完成 TLS 1.3、真实随机 HTTP 响应与双向 close_notify |
| 拒绝路径 | 错误根、域名、过期、移除根、篡改、错误代际均拒绝；证书失败不发应用请求 |
| 公共 CA 输入 | 118 个根在真实客体中成功解析；不是公网握手或 Firefox 策略资格 |
| 资源 | 每次调用后恢复 `[129525, 4, 2]`，含已启动网络服务的基线 |
| HTTPS 适配器 | 用最终 probe 的同一目标工具链独立编译通过；完整 Qt 消费者未运行 |
| 许可证材料 | 当前系统 10 项材料/SDK 副本匹配，无新增第三方运行库或内置 CA 文件 |

首次 guest 在进入内核前因宿主拒绝 Unix QMP socket 失败。此 runner 只用串口，
不需要 QMP；显式 `qmp_enabled=False` 后成功。保留首次失败 JSON/日志及最终
源绑定报告，没有把失败改写成通过，也没有改变宿主访问控制。后续再加入 leaf
非 CA 负例和精确 DER 检查后重新构建了最终系统/probe，并完整重跑。

## 复现

以下命令在 Preview 2 launcher 内执行，使用各自明确的输入路径和全新输出目录。
主机 OpenSSL 须支持受控过期证书的日期参数；CMake 是构建工具。

```sh
python3 tests/tls_trust_store_test.py --output build/p0_tls_host_final
python3 scripts/package_tls_trust_store.py \
  --pem "$XOS_CA_PEM" \
  --source-sha256 427c064216761a1e72a8b30f0d954d08cb6e4435a82091fb865afd20c8497285 \
  --source-url https://curl.se/ca/cacert.pem --generation 20261105 \
  --output build/p0_public_ca_final.bin
python3 tests/native_tls_guest.py prepare \
  --certificates build/p0_tls_certificates_final --trust-store \
  --public-trust-store build/p0_public_ca_final.bin
python3 src/ports/native_tls/build_probe.py \
  --archive "$XOS_MBEDTLS_ARCHIVE" --sdk "$XOS_GLIBC_SDK" \
  --test-root build/p0_tls_certificates_final/tls_test_root.h \
  --trust-fixtures build/p0_tls_certificates_final/tls_trust_fixtures.hpp \
  --output build/p0_tls_probe_final
XOS_LWIP_SOURCE_ARCHIVE="$XOS_LWIP_ARCHIVE" \
  python3 scripts/build.py --output-dir build/p0_tls_system_final
python3 tests/native_tls_guest.py test --system build/p0_tls_system_final \
  --probe build/p0_tls_probe_final --certificates build/p0_tls_certificates_final \
  --output build/p0_tls_guest_final
python3 scripts/license_audit.py --build build/p0_tls_system_final
```

官方 curl/Mozilla 2026-11-05 转换输入为 MPL-2.0；其额外策略限制和分发边界见
[契约](../contracts/tls_trust_store.md)。本 PR 只提交来源/digest/成员摘要，不
重新分发 PEM/DER bundle。生产部署必须另外选择并认证信任根策略。

## 证据与下一步

[summary.json](../reports/p0_tls_trust_store_20261127/summary.json) 记录实际
命令、工具、输入/输出身份与未运行项目。平铺 manifest 绑定公开叶子；完整系统
manifest 在规范化路径后压缩。原件 SHA-256 与公开副本 SHA-256 均保留。
完整串口日志已检查：只含新建测试盘、公开内核输出、测试证书摘要、随机 nonce
和计数；没有私人磁盘、私钥或真实账户内容。

本模块达到 P0-N4 的有界快照及显式更新/回滚范围。公开网络握手、可信物理时间、
硬件熵资格、并发 PSA、NetworkProcess、OCSP/CRL/自动更新和物理断电语义没有
在此取得资格；跨模块组合仍由 P0-I 绑定最终树验证。
