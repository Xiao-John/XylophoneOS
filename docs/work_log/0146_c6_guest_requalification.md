# 0146 技术债 C6 清偿：B1 改名的客体再验收（四套件全 PASS）

2026-10-31 · 分支 `codex/c6_guest_requal_20261031`（基线 `94549a9`，即 #39 合并后主线）。

## 1. 范围与产物

- 清偿 `docs/tech_debt.md` 条目 **C6**（#39 改名验收留下的客体 NOT_RUN）：
  `aurora_standard_button_guest` 3/3、`aurora_platform_guest --case render`
  13/13（11 张截屏）、`--case semantic` 5/5、`ssg_diff_guest --expected-checks 13`
  13/13（含 `stale_generation_since_resets`），宿主 `aurora_blur_cases`
  396 向量 + 6 拒绝全 PASS。证据 `docs/reports/c6_guest_requal_20261031/`。
- 附带清偿 0145 的 `qxos.moc` NOT_RUN：目标流水线中真实 host-moc 6.8.3
  重新生成了 `qxos.moc`，随各夹具收据记录。
- 随本组提交的修复（详见报告 checks.json FIXES_CARRIED）：
  `patches/0009-xos-freetype-no-mmap.patch`（现行树不打此补丁无法构建目标 Qt，
  属本组发现的潜在断链）、`patches/0010-xos-host-arm64-acle.patch`（宿主 arm64
  构建）、`qxos.cpp` 的 `mutable ::fonts fonts;`（目标 g++ `-Wchanges-meaning`
  在改名后拒绝该声明，宿主 clang 未拦）、`tests/ssg_diff_guest.py` 默认期望
  12→13（#29 新增用例未同步进套件默认值，此前按条数误判 FAIL）。

## 2. 选择与原因

- 全程按 C31：不绕过任何门。目标 Qt 只建七个库目标是复刻 E17 合格配置的
  原样（E17 构建日志 799 步止于 libQt6Widgets.a、零 plugin 边），不是偷工。
- 共享 `build/threading_sdk` 落后于主线（缺 `xos/display_client.hpp`），
  按"版本匹配 SDK"要求用 `build_threading_sdk.py --cpp` 现建（manifest
  `459e0935…`），不改共享目录。
- 夹具与套件逐一"先建后跑"：套件校验收据输入哈希，任何后续重建都会使
  先前收据失效（实测踩过）。
- ssg 套件带 `--expected-checks 13` 重跑并将默认值修为 13：13 项客体检查
  逐项皆 PASS，旧默认值属计数误判。

## 3. 执行的命令与证据

- 环境：Apple clang 21 / x86_64-elf-gcc 16.2.0 / Qt 6.8.3 私有源
  （sha256 `56001b90…` 与 source_lock 一致）/ binutils 2.47 预建 + 无前缀 shim /
  Pillow 11.3.0（用户提供源码包，PyPI 本网络不可达）。
- 关键链路：`prepare_gui_source.py`（0001–0010）→ 宿主 Qt 工具构建 →
  `configure_widgets.py` + 定向七库构建 → `build_threading_sdk.py --cpp` →
  `build_widgets_fixture.py` ×4 → 四套件（`scripts/build.py` 分支镜像
  `8a7eb736…`）。精确命令与哈希在报告 `checks.json` 与各夹具收据。
- 结果汇总见报告 README 表；`evidence/` 含四份 report.json 与日志（gzip）。

## 4. 通过 / 失败 / 未运行

- 通过：上列四套件 + blur 宿主用例 + moc 再生成；`git diff --check`、
  `docs_consistency`、`abi_doc_consistency` 于提交前复跑（见 PR）。
- 失败（过程记录，未改判）：首次套件尝试因收据陈旧、输出目录残留、
  PIL 缺失各失败一轮，均修正环境后重跑，失败日志未冒充通过。
- 未运行：`aurora_platform_guest --case dash`（需 desktop/session/gap/apps
  夹具链，不属 C6 出账范围）。

## 5. 下一步

- 用户 review/合并 PR；合并后把 C6 移入"已清偿"。
- 环境备忘（非仓库债）：共享 `build/threading_sdk` 落后主线，Qt 夹具工作
  请按本组方式现建版本匹配 SDK；宿主跑套件需要 Pillow。
- 不能误认成已实现：dash 套件与 D 系功能债不在本清偿范围。
