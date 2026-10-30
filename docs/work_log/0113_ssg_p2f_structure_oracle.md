# 0113 — SSG-P2F 独立结构与文本验收

继续 fork Draft PR #10，基线 `9a739c7`。实现提交 `0a63648`，宿主点击尺寸修正 `a81b4fd`。
本轮只推进 Gate A 的 A1，不合并 main 或依赖，不修改 kernel、公共系统 ABI、QPA、驱动。
AI-native/SSG 是用户态研究，本记录不批准项目宪法变更。

新增测试构建专用的独立 liteHTML 递归参考，不复用分页 DFS/IDs/完成判断，
在真实 IPC 前后核对同一文档；严格验证 Consumer 节点映射、顺序、精确文本与链接。
正常 Browser 不含 Oracle。Consumer 加强分页字段、根与父关系等局部验证，仍明确
`ORACLE_REQUIRED`，没有将局部一致性替代完整性证据。

真实新构建与 QEMU 验收：

- 原 P2D：32 节点，`8,8,8,8,0`，独立结构/文本对照通过。
- 新 P2F：267 节点、34 页，独立结构/文本对照通过。
- 单可见链接：Consumer 坐标 `(56,326)`，真实 800×600 framebuffer 内 PS/2 命中 `start.html`。
- 1025 UTF-16 单位文本：明确 RESOURCE_LIMIT，Consumer 未完成并拒绝，资源恢复。
- 普通 Browser：原 P1/小 Browser 16 项外层检查通过；原非分页 Browser 7 项原断言通过。
- 非分页首次 snapshot 仍因 TIME 截断，不声称固定时间预算问题根治；旧失败证据保留。
- 首次 QMP socket 沙箱启动失败、后续真实通过以及构建失败/恢复材料分别保存。
- 52 项宿主 verifier 测试通过，但未混同为客体验收。

详细结果、输入哈希、完整 IPC、独立 Oracle、PS/2、资源、构建与独立审计材料见
[本轮报告](../reports/ssg_p2f_20261030/README.md)。

A1 为 PASSED_SCOPED。Gate A 整体仍未资格认定，所有渲染几何和全局遮挡未证明；
Gate B/C、过滤查询、4096 ID 边界、完整游标生命周期、Notes 安全与 LocalPilot 不在本轮通过范围。
没有 GitHub CI 通过声称，没有合并操作。
