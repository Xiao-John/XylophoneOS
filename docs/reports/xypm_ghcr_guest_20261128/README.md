<!-- SPDX-License-Identifier: Apache-2.0 -->
# 公开 GHCR 的 xypm 客体验收

2026-11-28。在 `main` 基线 `c2947d28` 上重新构建系统和同 profile 的
glibc xypm，使用 QEMU 11.1.2 和新建的 FAT 工作盘验收。源提交和构建摘要见
[qualification.json](qualification.json)。

客体通过原生 Net2 和 TLS 从公开仓库 `ghcr.io/xiao-john/xypm-smoke` 匿名取令牌，
按不可变摘要取得 OCI 清单和 XPK。下载器校验层长度、SHA-256 和 XPK profile。
随后在同一客体运行维护安装，确认提交并完成恢复清尾。新的 xypm 进程查询到
`xos.xypm-smoke` 版本 `0.0.1-r0`，摘要和 profile 匹配。关停 QEMU 后从同一工作盘
导出 `/var/lib/xypm/db.json`，再次核对已安装记录。

- [guest_excerpt.txt](guest_excerpt.txt) 是原始测试回执的派生摘录，逐行保留成功标记。
  原始回执留在本地，公开摘录省去命令回显、路由地址和其他运行期诊断。
- [db.json](db.json) 是关停后逐字节导出的数据库。
- [manifest.json](manifest.json) 覆盖本目录全部证据文件。

复跑时用 `scripts/build.py --quiet-demos-on-launch --net-static-profile PROFILE`
构建允许 GHCR 和 GitHub 对象存储 HTTPS 出站的镜像。按
[接入说明](../../plans/xypm_ghcr.md#客体下载及安装)构建同 profile 的 glibc xypm，
再运行 `tests/package_ghcr_guest.py`，传入本目录固定的 OCI 与 XPK 摘要、独立的 CA
快照及其生成号和摘要，以及对应出站规则的 IPv4 地址。工具自行建盘，关停后导出数据库。

本次覆盖单个公开 XPK、显式 IPv4 和固定 CA 快照。私有仓库、自动 DNS、断电恢复和
已签名发行版的客体回归未运行。已签名发行版通过 30 项宿主 EVP 回归。

常规 C++ 入口通过语法检查。另试 legacy newlib 的完整 SDK 构建时，本机缓存与
冻结 profile 的摘要不匹配，新镜像随附的 SDK 也缺少该 profile 需要的 C++ 运行库，
两次均在编译前停止。仓库级报告清单检查仍报告主线已有的格式问题，本报告的
平铺清单独立核验通过。
