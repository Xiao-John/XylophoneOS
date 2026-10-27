# xypm：实现摘要

截至2026-10-27。当前契约与待办见[包管理计划](../plans/packages.md)。

## 已实现

- 正式名称xypm，包ID xos.xypm，/usr/bin/xypm，数据库/var/lib/xypm/db.json与index.tsv；
  .xpk v1容器保持。旧xpm/xpkg数据库存在时拒绝创建第二套归属库，不自动迁移。
- P0：独立SDK/profile、受限ustar/JSON/schema/摘要/ELF准入、精确依赖与产物打包。
- P1宿主事务：源盘只读复制到独立候选，排他会话、拒绝覆盖输出；校验归属/依赖/真实FAT别名，
  写后回读校验，用同文件系统硬链接发布；保护用户文件。64包/8192归属文件、数据库1MiB。
- P1客体查询：xsh/dash同一list/info与状态；临时导出使用会话UUID+序列，宿主wbx拒绝覆盖。
- P2-1：sys62维护准入、files23/24写租约、maint-run/recover/status；worker失败保留屏障，
  无打开实例/staging后才释放，权限依可信身份，不依程序名。内存屏障不是持久事务。
- P2-2：原生verify/plan install|upgrade、包/数据库/index一致性与SHA/UTF-8/整数有界校验；
  executable额外核ELF64/PT_LOAD/PT_TLS、权限/重叠/入口/页预算，与宿主规则对齐。只读不执行。

## 证据与未完成

P0宿主16组，P1宿主12组、双Shell/重启客体10项通过。P2-1最终4c79f3a789dcff61上8/8，
镜像4950c4c2fb53c36ac7cf36d4b6e40954c5b36507f8fc11207b867b54520b16ee，资源[130345,2,0]。
0054修复后当前维护专项9项通过，见[审计摘要](delivery_audit.md)。旧维护sys54/file20–21
已在集成时移到62/23–24；旧报告编号不改写，当前以ABI登记为准。

P2-2冻结single_b2_v1 SDK编译/打包完成，ELF补充后cache7247032b2da0165bcbb6、包摘要
98da85667d646bcadb6e6c86e375de2f05a6aaf7e1331d1109749de94bcbf3ee，36文件；
状态仍packed_guest_not_run。guest有效/畸形夹具、P2-3持久journal/恢复、P2-4写命令、
P3仓库/签名未完成；不得据本摘要开放客体写命令或将SDK白名单迁移推定成功。

## 合并来源

原文按[source_index.json](source_index.json)记录的提交、路径和SHA256恢复；以下锚点保留旧引用。

<a id="log-0032_package_management"></a>
- `docs/history/packages.md#log-0032_package_management`
<a id="log-0035_package_p0"></a>
- `docs/history/packages.md#log-0035_package_p0`
<a id="log-0044_xypm_p1"></a>
- `docs/history/packages.md#log-0044_xypm_p1`
<a id="log-0048_xypm_p2_maintenance"></a>
- `docs/history/packages.md#log-0048_xypm_p2_maintenance`
<a id="log-0051_xypm_p2_verify_plan"></a>
- `docs/history/packages.md#log-0051_xypm_p2_verify_plan`
<a id="log-0055_xypm_p2_elf_validation"></a>
- `docs/history/packages.md#log-0055_xypm_p2_elf_validation`
