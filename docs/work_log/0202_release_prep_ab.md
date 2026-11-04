# 0202 — 发版 0.0.2-1103 前置 A/B 步骤执行记录

2026-11-04。发版准备：A（前置清障/构建）与 B（Qt 许可关口）执行记录。
源码基点：main `6fe330ce`（detach 定格）。

## A. 前置清障与构建

1. **A1 清障**：删除误跑遗留 `build/releases/0.0.2-1103/sources/`（538M）与
   `source_manifest.json`——`package_release_materials.py` 拒覆盖旧目录，正式打包前必须干净。
2. **A2 源码定格**：`git switch --detach origin/main` → `6fe330ce`
   （含 PR #70/#71/#72：GNU NOTICE/GFDL、GCC 成员裁定、Qt 文本覆盖）。
3. **A3 全量构建**：
   - `python3 scripts/build.py` → EXIT 0，build_id `8356e45af316fc93`
     （首跑 `7cc38437aa823d84`；因 open_items 注记变更刷新 SDK 后重跑得新 id）；
     kernel 512080 bytes，`xos.iso` + `xos-install.iso` + `real_mode.img`。
   - `scripts/build_dash.py`：首轮因工作区被超时 SIGTERM 脏状态卡死（mksyntax/mknodes
     0% CPU），清 `.cache/xos_seed/dash/<key>` 后重建（进行中，完成后补记 sha）。
   - `make install-iso` 随 `build.py` 内嵌产出 install ISO。

## B. Qt 许可关口（用户指令：下次 release 打入 Qt）

1. **B4 打包核验**（`qt_static_redistribution_packaging_verification`）：
   `docs/reports/qt_static_distribution_20261103/packaging_verification_20261104.json`
   — **25/25 PASS**：源包 sha 钉定、10 静态库 sha 匹配、10 补丁齐、13 份 Qt 文本登记、
   构建配方脚本 sha 匹配。打包动作时仍须对最终随包资产做哈希复核（步骤 D）。
2. **B5 安全审查**（`qt_static_redistribution_security_review`）：
   `security_review_20261104.json` — **PASS_WITH_LIMITS**：供应链钉定、构建隔离
   （48 项特性显式关闭含网络/dlopen）、静态-only、补丁无异常载荷模式；
   **CVE 扫描 NOT_RUN**（离线）、运行时渗透 NOT_RUN（范围外）——残余风险如实记录，
   由发版负责人接受或联网后补查。
3. **E16 distribution 门**：E16 `qualification.json` 的 `distribution: NOT_RUN`
   无独立 runner；其语义 = Qt 打包分发路径未演练。**B4 + 步骤 D 实包核验即该门的执行**，
   不另造 runner。
4. **license_audit**：`PASS: 9 license materials | build 8356e45af316fc93 |
   open license items: 0`——**0 open**。
5. **登记更新**：`REDISTRIBUTION.md` §0 改写（本版按指令随包 Qt，门槛已执行）；
   `open_items.json` 两 Qt deferred 项 summary 注记 B4/B5 进度（状态仍 deferred 至
   D 步实包复核完成）；`qt_static_distribution_20261103/manifest.json` 重生成。

## 待续（C/D 步）

- dash 构建完成 → 确认 install ISO 绑定。
- C：定向 gate 选型与 smoke（release smoke 对齐 11/11 口径）。
- D：新版本目录冻结（含 **Qt 资产**：静态库+头文件+配方+补丁+许可文本+对应源码）、
  随包哈希复核（B4 收口）、上传/tag/release/回执。
- Qt 落位方案（拟）：独立资产 `xylophoneos_revival_0.0.2-1103_qt6_static.tar.gz`
  （不动 `verify_sdk` 严格集）；源码材料含 qtbase 源包 + 10 补丁。
