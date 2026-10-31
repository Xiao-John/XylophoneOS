# 0107 — Browser SSG fragment integrity

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
