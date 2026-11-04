# 归档成员来源契约（archive_member_provenance）

2026-11-03 · 与 [evidence_integrity](evidence_integrity.md)（报告目录）、
[abi_registry](abi_registry.md)（syscall 编号）同级的专项契约。宪法依据：C10（固定来源/
哈希/补丁，材料检查不冒称逐成员法律审计）、C31（建设基础而非制造已经完成的假象）。

## 为什么需要它

D7 收口时为回答"这个静态归档成员是从哪个源文件编出来的"，三份脚本各自发明了一套
考古阶梯（`.deps` → 构建日志 → 字节比对 → `nm`/`c++filt` 符号反查 → 词干文本），
合计耗时以小时计，且仍有成员无法归属（GCC 397/407；Qt 走到第三版才靠"归档成员与构建
对象字节一致"拿到 1522/1522）。**根因不是脚本难写，
而是构建当时明明知道成员来源，却没有登记下来。** 本契约把"造归档时顺手记一笔"定为规则。

## 要求

1. **凡进入"已验收/拟分发"状态的静态归档（`.a`），必须在创建它的同一次构建中产出
   `member_manifest.json`**，与归档同目录或由构建 manifest 引用其 sha256。
2. 清单格式（确定性、键排序、无本机绝对路径）：

```json
{
  "version": 1,
  "archive": "build/<tree>/lib/libX.a",
  "build_id": "<system build id>",
  "generator": "<script path that emitted it>",
  "members": [
    {"member": "name.o", "source": "<仓库相对源路径>", "source_sha256": "<sha256>",
     "declaration_class": "<spdx|bsd_like|lgpl|gpl|...>"}
  ]
}
```

3. **来源必须是构建过程的一手记录**（编译命令行、`.d`/`.Po` 依赖、对象与归档的字节
   一致性），不得用"同名文件""符号反查"这类推导结果冒充；推导只能作为**回退**并在
   字段里标 `derived: true`。
4. 归档、源文件或构建配置任一变化后，清单必须随构建重新生成；旧清单不得跨构建复用。
5. 审计口径：`scripts/license_audit.py` 与任何"逐成员"声称只读清单与校验器，**不再
   现场考古**；校验器为统一实现（`scripts/archive_member_map.py`，由三份现有脚本抽取，
   见 `docs/tech_debt.md` D12），比对"清单 ↔ 归档实际成员 ↔ 源文件哈希"。

## 老人老办法（分界线）

本契约**不追溯**已发布与既有构建：

| 归档 | 现状（推导映射，非本契约产物） | 生效点 |
|---|---|---|
| newlib `libc.a`/`libm.a` | 1053/1053（依赖记录） | 下一次 newlib 重建 |
| GCC 运行库三件套 | 397/407，10 个未解析 | 下一次 GCC/运行库重建 |
| Qt widgets/widgets2 静态库 | 1522/1522（对象与归档字节一致，属一手记录，但非本契约产出的 `member_manifest.json`） | 下一次 Qt 构建 |

上述推导结果必须始终标注为"推导"，**不得**改写成"契约已满足"。推导报告在
`licenses/open_items.json` 登记，残余缺口逐条带退出条件。

## 执行与罚则

- `scripts/license_audit.py` 从 `licenses/open_items.json` 派生 `not_completed` 并硬校验：
  证据缺失、状态非法、`open` 却无退出条件、或证据目录缺平铺 `manifest.json` → 审计失败。
- 任何声称"逐成员已审"的归档，必须满足其一：①有本契约的 `member_manifest.json`；
  ②有推导报告并在开放项登记处逐条登记残余。
- 违反本契约即为 C31 违例：把推导或未完成项包装成完成。

## 未覆盖

本契约只管"成员 → 源 → 声明类别"的**可追溯性**，不提供法律意见、不授予发行资格，
也不替代 [evidence_integrity](evidence_integrity.md) 对报告目录的哈希要求。
