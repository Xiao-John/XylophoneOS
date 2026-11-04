# 0191 — Browser SSG fragment integrity

2026-10-30. On SSG parent `a4c61619`, replace visibility inferred from a union
rectangle with individually clipped real liteHTML render fragments. The bounded
query emits explicit incomplete-fragment status and a stable query scope; the
scope-aware Diff behavior depends on the SDK follow-up in fork PR #3.

Built with the E17 Qt 6.8.3 SDK and ran `tests/ssg_diff_guest.py` on the geometry
fixture and `tests/aurora_platform_guest.py --case browser` against a local
Desktop + SDK-fixes + Browser-fix combination. Six target-side geometry checks
and seven actual Browser/SSG guest gates passed. Actual commands, source/ELF/image
hashes, JSON/serial and scanout are in [the report](../reports/browser_fragment_integrity_20261030/README.md).

No kernel, system ABI, QPA, driver, network or file-service change. The result
does not establish whole-screen occlusion, cross-process authority, forms,
iframe, Canvas, JavaScript or complete modern-Web behavior. Integrate the SDK
repair first and rerun affected Browser/Notes gates after every base change.

The original SSG work log linked to a combined qualification file introduced
only by the later Desktop PR, so the SSG branch's standalone docs check failed.
Its frozen SSG evidence link now points to the report present on that branch;
the later combined index remains in the Desktop review unit.

2026-11-01 主线 72bfacb 及 #40 的审查导出上重新构建，Browser 七项客体检查通过；此前的几何结果仍绑定原输入。


## 维护者合并记录（2026-11-04）

- 编号 0188→0191（main 已占 0188/0189/0190；按 README「自 0188 起全局唯一」规则让号）。
- 评审阻塞 3 的去重子项按**豁免**处理：`browser-dom-first.png` 与主线
  `aurora_ssg_consumers_20261101/browser/` 同 sha 属跨目录冗余，但被本套
  `browser/report.json` 引用且列入 manifest，删除构成证据语义修订
  （evidence_integrity §4 需另行工作记录）；`serial.log.gz == guest_serial.log.gz`
  为主线系统性旧惯例（先例 `631f85cc`）。豁免不等于去重已完成；如需清理，
  另开任务按契约做语义修订记录。
