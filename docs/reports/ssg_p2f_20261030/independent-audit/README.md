# 独立复算审计：已记录的真实客体证据

此目录不是另一次 QEMU 运行。审计器只读取本轮已经保存的客体串口、Oracle、IPC payload、构建收据和输入文件；它不启动 Guest，也不读取 HTML 来预测或生成期望 DOM。

`audit.py` 不导入 `tests/ssg_browser_structure.py`。它另行完成串口帧解码，把 Consumer 的 ID/parent ID 构成邻接表，再递归重建规范化路径及前序记录，与客体 before/after Oracle 逐节点、逐字段完整比较，并独立计算 UTF-8 netstring 摘要。每个成功记录都核对文本、href、子节点数量、父子关系、兄弟序和 Consumer 导出的对照行。

审计还核对原始串口与导出的 payload、重建 `.wire` 文件、输入摘要、Browser ELF/receipt、进程身份、退出结果及资源计数。`.wire` 的头部是根据协议字段重建，payload 来自 Consumer 的实际日志，不能将其描述成额外抓取的原始线缆数据。

## 首次实际审计

命令从仓库根目录执行：

```bash
python3 docs/reports/ssg_p2f_20261030/independent-audit/audit.py \
  --runs-root build/ssg_p2f_runs \
  --output docs/reports/ssg_p2f_20261030/independent-audit/audit-results-initial.json
```

| 本轮记录 | 独立复算结果 | 说明 |
|---|---|---|
| `p2d-oracle-02` | `PASSED_SCOPED` | 32 节点；5 页，8/8/8/8/0；10 element、20 text、2 link |
| `p2f-oracle-01` | `PASSED_SCOPED` | 267 节点；34 页，33×8+3；52 element、206 text、9 link |
| `text-limit-01` | `PASSED_SCOPED`：预期资源拒绝 | Oracle 7 节点，其中前序 ordinal 5、路径 `0/1/0/0` 的文本为 1025 UTF-16 单位；终末 `RESOURCE_LIMIT`，Consumer 未接受完整性 |
| `p2d-oracle-01` | `FAILED_ATTEMPT_PRESERVED` | QEMU 进程在建立 QMP Unix socket 时因 `Operation not permitted` 退出；串口 0 字节，没有观察到客体启动 |

完整摘要、版本绑定和资源数值见 `audit-results-initial.json`。

`p2d-oracle-02` 的单链接证据也被复算：实际截图 800×600，Consumer 节点 13 的 `start.html` 片段包含点 (56, 326)；已记录的相对鼠标位移收敛到该点，随后只有一次左键按下/松开，客体产生 `BROWSER_LINK target=/web/start.html` 并加载目标。该输入发生在分页终止响应之后。本审计只确认这一可见链接，不确认全局几何、窗口遮挡或分页期间交互恢复。

## 版本与资源边界

- A1 通过限定于两份固定输入及对应的实际测试构建，不能推广为所有网页都完整。
- Oracle before/after 相等不等于通过动态变化、失效和重同步测试。
- 分页 Probe 保留显示服务运行：退出后资源恢复到显示服务基线 `[130235, 3, 1]`；系统启动且未开启显示服务的基线为 `[130279, 2, 0]`，不能混为一谈。
- Gate A 整体、全局渲染片段和视口可见性仍未资格认定；Gate B、C 未运行；性能未资格认定。
- 后续 Probe 单独修正实际截图尺寸读取，不改写本目录所审计的旧运行。若当前脚本内容已经不同，审计器仅在记录注明干净 checkout 时读取其精确 Git blob 核对原版本，结果明确标为 `MATCH_RECORDED_CLEAN_GIT_BLOB`。
- Browser 构建收据中的全部实际输入仍逐一复算；源码仓库和原始构建产物不可用时，审计器会拒绝声称这些绑定已验证。

后续如产生 `p2d-oracle-03`，应再次显式运行审计并保存新结果文件，保留 initial 记录：

```bash
python3 docs/reports/ssg_p2f_20261030/independent-audit/audit.py \
  --runs-root build/ssg_p2f_runs \
  --positive p2d-oracle-03 p2f-oracle-01 \
  --output docs/reports/ssg_p2f_20261030/independent-audit/audit-results-final.json
```

## 最终实际审计

上述 final 命令已实际执行成功。`p2d-oracle-03` 在干净 checkout `a81b4fd7ab18ec09e87b311e8fe89cf4464fb63c` 运行，32 节点五页全量相等，链接节点 13 的 (56, 326) 命中复算通过；新报告的 `screen_size=[800,600]` 与实际 PNG 尺寸相符。`p2f-oracle-01`、`text-limit-01` 和首次失败的保留检查再次通过。

`audit.py` 新增了对报告所记 `screen_size` 与实际 PNG 尺寸的显式比较。首次审计的脚本另存为 `audit-initial.py`，其哈希与 `audit-results-initial.json` 一致；initial 结果未覆盖。final 结果记录增强后脚本的独立哈希。

另运行 `audit_regressions.py`，生成 `regression-audit.json`。它只审计已记录的回归，没有启动新客体：

- `p1-regression-01`：16 项外层检查 `PASSED_SCOPED`，17 项 Notes Consumer 和 8 项 Browser Consumer 检查均为 PASS，资源回到 `[130279,2,0]`。
- `large-regression-01`：7 项原非分页 Browser 检查 `PASSED`；滚动 Diff 实际 `OK`、未截断且包含变化节点。
- 两个回归脚本与基线 `9a739c7052d66dd75c0a0aceb807b0e4aa2fc16f` 的文件字节完全一致，没有降低旧断言。
- **旧非分页测试的首次 snapshot 仍因 TIME 被截断；后来重新导航所得完整基线与滚动 Diff 通过。** 应将本轮结果表述为原断言的真实通过，不能宣称 30 ms 非分页时间上限导致的截断已从根本上解决。
