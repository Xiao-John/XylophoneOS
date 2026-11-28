<!-- SPDX-License-Identifier: Apache-2.0 -->
# xypm GitHub Container Registry 接入

基线 `3028573c852d4db7e200df3c1a5348a3780ce745`。本页是待实施计划，不是已验能力。
GitHub Packages 不提供 XPK 原生格式；首批使用公开 GHCR OCI 制品承载现有 XPK，
不将 OCI 层当成可执行的容器映像，也不改变 XPK v1 的安装或恢复规则。

1. 冻结 OCI 清单的媒体类型、单包身份、摘要和长度绑定；使用明确指定的不可变
   manifest 摘要，严格限制 JSON、响应头、重定向与包体。验证 OCI 摘要后仍运行现有
   XPK 格式、profile 和完整性校验；清单摘要由独立可信渠道提供，不能将自报摘要
   视为发布者认证。私有包和凭据管理另行设计。
2. 使用客体网络服务与版本化信任库，完成 HTTPS、GHCR bearer challenge、token
   服务及 blob 重定向；限定 HTTPS、授权服务和重定向目标，不能把 bearer token
   泄露给其他来源。对 DNS、证书、主机名、时钟、熵和过期验证失败直接拒绝。
3. 流式写入独立缓存临时文件，限制长度并计算摘要；完整验证后才发布缓存项。
   获取结束并释放网络资源后，再由现有维护会话执行单包事务；失败或中断不修改
   已安装数据库。跨包自动原子更新与防回滚不在本次假设中。
4. 测试分层：宿主解析/恶意响应及分片、重定向和截断；受控客体 HTTPS 与真实包
   的取得、校验、安装、重启及故障恢复；最后单列真实 GHCR 公开制品端到端验证。
   每层记录实际输入、配置和结果，公开互联网、可信时间及物理断电未验不得冒称通过。

现有 N4 的公共 CA 快照只验证了客体解析，不代表公开互联网握手通过；浏览器 HTTP
适配器限 1 MiB 且拒绝 transfer-encoding，不能直接承担大 XPK 的下载。实际实现必须
处理 GHCR 对 token 和 blob 响应使用的帧格式及独立源，而不是绕过 TLS 校验。

## 宿主先行入口

`python3 scripts/xypm.py ghcr-fetch OWNER/NAME sha256:<manifest摘要> --profile PROFILE -o APP.xpk`
使用宿主 HTTPS 请求限定范围的匿名 pull token，按摘要下载 OCI manifest，再下载并校验
唯一的 XPK 层。清单的 `artifactType` 和层的 `mediaType` 均为
`application/vnd.xos.xpk.v1`，config 使用 OCI empty descriptor。只允许 GHCR blob
跳转至 `pkg-containers.githubusercontent.com`，不转发 bearer token。输出完整通过
XPK profile 校验后才可见，可继续交给现有离线事务。客体网络客户端仍按上面的阶段推进。

规范依据：[OCI manifest](https://github.com/opencontainers/image-spec/blob/main/manifest.md)
与 [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)。

## 客体下载及安装

使用 `src/ports/native_tls/build_probe.py --xypm-installer --xypm-profile-id PROFILE_ID`
构建包含 `ghcr-fetch`、维护安装与数据库回读的 glibc xypm ELF，另传锁定的
Mbed TLS 归档、已验签的 glibc SDK 和新输出目录。下载器读取部署方提供的 CA 快照。
下载和安装使用独立调用。
在客体中执行以下流程，信任快照的生成号和摘要由部署方独立提供。安装镜像须授权
明确的 GHCR 和对象存储 IPv4 地址的 TCP 443 出站。

```text
exec-file /usr/bin/xypm ghcr-fetch NET_PID GHCR_IPV4 BLOB_IPV4 /ca.bin CA_GENERATION CA_SHA256 OWNER/NAME sha256:MANIFEST_SHA256 /fetch
net-stop
audio stop
maint-run /usr/bin/xypm install /fetch/package.xpk --sha256 XPK_SHA256
exec-file /usr/bin/xypm info PACKAGE_ID
```

下载器只用 HTTP/1.0 的 Content-Length 响应，通过已有 TLS 验证链路检查证书、SNI、
时间和有序关闭。GHCR 匿名令牌按仓库缩限，仅发送给 GHCR。blob 最多允许一次到
固定 GitHub 存储主机的 HTTPS 跳转。输出必须是新目录，先写 `package.part`，
完整验证层摘要和包内清单后再改名。安装命令再次按摘要验证同一包；原生端暂用
显式固定 IPv4 路由，且要求安装 profile 提前授权，DNS 变化需要更新该验证配置。

`tests/package_ghcr_guest.py` 的安装模式要求输入公开 OCI 清单摘要、期望的 XPK ID、
相同 profile 的 glibc xypm、下载器和独立 CA pin。测试在一张临时 FAT 盘执行下载、
安装及数据库回读。无安装参数的探测模式只验证真实 GHCR 上的非 XPK 拒绝路径，
有 `--download-sha256` 时只验证下载并从客体盘导出核对。测试端口构建只针对受控服务。
