# HTTP 有界流式响应

基线 `3028573c852d4db7e200df3c1a5348a3780ce745`。增加带调用方正文上限、
头部工作区和 sink 回调的 Content-Length 流式读取，以及复用 native TLS 的 HTTPS
入口。浏览器原有 1 MiB 接口保持原上限。结果只有在完整正文和连接结束均成功后
有效；HTTPS 还须成功完成 TLS 关闭。所有状态码的正文都会到达 sink，调用方须在
接受内容前核对状态并在任何错误时丢弃临时输出。传输和解析仍拒绝 chunked、压缩
编码、重复 Content-Length 和额外字节；重定向、认证及落盘由上层负责。

在 macOS 主机执行 `python3 tests/browser_http_stream_test.py`：ASan/UBSan 通过，
覆盖 2 MiB 以上正文、分片、上限、截断、额外字节、重复长度、chunked 拒绝、
零长度与 sink 错误。`python3 tests/browser_http_test.py` 通过 212 项和 4096 个
畸形向量；`git diff --check` 通过。

未运行：目标 SDK 编译、真实 TLS 和客体网络；本次没有接入 xypm，也未实现 GHCR
认证或下载。下一步用匹配的 glibc SDK 与 Mbed TLS 构建目标，运行受控 HTTPS
客体大文件和截断测试，之后才接入缓存和 GHCR 客户端。

## 目标与 GHCR 跟进

- `http.cpp` 和 `transport.cpp` 已用 `x86_64-elf-g++` 编译为 x86‑64 ELF 对象。
  `scripts/build.py --output-dir build/xypm_https_system --quiet-demos-on-launch`
  构建出客体测试镜像 `9f25bb00285096f8`。锁定 Mbed TLS 4.1.1 归档已核对
  SHA‑256 `3359a349e23db3d5536fcee032ae7b2ecbfc08972fab643089b5cbf2a375c98c`。
- TLS 探针现在链接原生 HTTPS 适配器。客体测试检查带随机挑战的 2 MiB 以上正文，
  以及服务端使用正常 TLS 关闭而少发一个正文字节的拒绝路径。
- 宿主 `ghcr-fetch` 通过固定 manifest 摘要和严格的 OCI XPK 描述符提取包，
  完成流式暂存、大小检查、摘要与 profile 校验后发布文件。宿主实测 GHCR 公开
  token 端点。三项受控测试核对真实 XPK、无效下载的清理和重定向令牌隔离。
  `python3 tests/package_p3_repository.py` 的 50 项测试通过。
- macOS 使用 GNU Make 4.4.1、GNU Patch、Coreutils、Bison 3.8.2 和 gpgv 建成
  `build/xypm_https_sdk_full`，清单状态为 `static_sdk_built`。原生 TLS 探针在该
  SDK 上编译并静态链接为 x86‑64 ELF。早期构建分别遇到 BSD Patch 失败、系统
  Make/Bison 版本过旧和并行生成版本表失败。
- 第一次加入大响应后，7 项原有 TLS 场景通过，新增场景暴露了整次下载截止时间不能
  超过单 IPC 30 秒的限制。改用合规的 30 秒期限后握手通过，正文接收超时。随后将
  整体期限与单次请求期限拆开，每次操作取两者允许的较早期限。
- QEMU 11.1.2 对最终镜像 `d9e817940d51e2d4` 返回 `passed_subset`，10 项通过。
  客体逐字节核对 2,097,159 字节并完成双向 TLS 关闭。少一字节的响应即使收到对端
  TLS close_notify 也被拒绝。两项分别耗时约 66 和 64 秒，网络交换后资源回到
  `129501 / 4 / 2`。本地回执在 `build/xypm_https_guest_window/report.json`。
  原生 xypm 直连 GHCR、公开 XPK 拉取和最大包体吞吐未验。

## 原生 GHCR 跟进

- glibc 版 xypm 增加 `ghcr-fetch` 分派。下载器是同盘独立静态 ELF，复用 Net2、
  版本化 CA、原生流式 HTTP 和 XPK 校验器。安装仍使用维护租约入口。
- 在镜像 `30b37e53efc1a94a` 用 QEMU 客体连接真实 GHCR，取得公开令牌并校验
  `homebrew/core/gawk` 的固定 OCI 清单摘要，随后拒绝非 XPK 清单，进程正常回收。
  回执 `build/xypm_ghcr_live_verified/report.json`。
- 受控 TLS 测试在客体下载实际 XPK，验证后写入 FAT，再停机导出与原始 XPK 对比
  SHA-256 一致。回执 `build/xypm_ghcr_controlled_guest/report.json`。
- 现有 P3 的 50 项回归及宿主 GHCR 的 3 项回归通过。公开 XPK 下载与安装、glibc
  分派及该安装模式尚未实际通过。未定位到可用公开制品，列表 API 缺读包授权。
  本地冻结 newlib SDK 也无法从当前源码构建安装器，缺少新版文件客户端方法；
  最终安装应采用与目标 XPK 同 profile 的当前 glibc C++ SDK。
- 宿主另查实际 GHCR blob 响应，确认该公开容器层返回 307、长度 0，
  目标为 `pkg-containers.githubusercontent.com`，目标响应声明固定长度。该检查
  未将容器层作为 XPK，也未验证客体 CDN 下载。

## GHCR 验收包发布与安装回读

- 最小原生数据包 `xos.xypm-smoke` 为 20,480 字节，包内有标记文件、项目许可证
  和回执。XPK SHA-256 `ac5ebd3839a58d2992d769b6aa5816a218f80777856101f001cd38ce9530b795`。
  已上传 `ghcr.io/xiao-john/xypm-smoke:smoke-v1`，OCI 清单摘要
  `sha256:cffcf1a0c10178a5b72df199a23382ecfa58927f00c8fe11478b9ee7470658c7`。
- 此 glibc SDK 对初版 `execv` 分派返回 ENOTSUP。验收用 glibc xypm 直接链接下载器，
  与安装器共用 `xos-x86_64-glibc-ghcr-smoke-v1` profile。受控 TLS 的 QEMU 回放中
  下载并验证了待公开的同一 XPK，安装进入 committed 并完成恢复清尾。
  客体 `xypm info` 和停机后导出的 `/var/lib/xypm/db.json` 同时确认包 ID、摘要和
  profile。回执 `build/xypm_ghcr_smoke_controlled_db/report.json`。
- 上传后的包可见性为 Private，匿名拉取返回 HTTP 401。公开后需重跑同一 OCI 清单的
  真实 GHCR 客体回放，受控安装证据不能替代实网验收。

包公开后，同 profile 的 glibc xypm 在 QEMU 镜像 `30b37e53efc1a94a` 完成真实
GHCR 验收。以固定 OCI 摘要取得匿名令牌和 XPK，客体计算出的 XPK SHA-256 与
发布前一致。维护命令完成提交和恢复清尾。新的 xypm 进程回读包版本 `0.0.1-r0`、
profile 和摘要。停机导出的实际 `/var/lib/xypm/db.json` 再次核对这三项，数据库
SHA-256 是 `f4d782a09dc40be788e44f9152a78ab28b13fa4f3cca9af2f5da90fe47e1ffbd`。
执行入口为 `tests/package_ghcr_guest.py`，记录在
`build/xypm_ghcr_public_guest/report.json` 和 `build/xypm_ghcr_public_guest/db.json`。
该验收使用显式授权的 IPv4 路由和钉住摘要的 CA 快照。

## 主线兼容性回放

以 `main` 的 `c2947d28` 为基线，保留认证发行命令并重新构建系统和 glibc xypm。
在新镜像 `faa268574f3d5577` 再次从真实公开 GHCR 下载、校验、安装并回读数据库。
构建绑定、客体摘录、停机数据库和宿主回归见
[公开 GHCR 客体验收](../reports/xypm_ghcr_guest_20261128/README.md)。
