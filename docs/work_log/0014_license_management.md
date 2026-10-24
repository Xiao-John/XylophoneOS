# 0014：许可证管理确认

2026-10-24；本记录只确认许可管理，不改变 E08 的实现或验收状态。

用户指定新代码使用 APL-2.0，按 Apache License 2.0、SPDX `Apache-2.0`
落实。策略入口为 `docs/licensing.md`，协作纪律见 `docs/Discipline.md`，
根目录 `LICENSE`/`NOTICE` 说明范围；历史 MIT 文本及基线清单保留在
`licenses/`，既有授权不撤销，第三方原条款不覆盖。

对照本地 `src/third_party/newlib/COPYING.NEWLIB` 与官方同名材料：newlib
是多来源组件集合，单文件可能自带适用条款，不能整体标为 LGPL。
本地第 21/22 节 LGPL 组件带 Linux target 限定；这也不代替当前
`libc.a`/`libm.a` 的逐成员来源与许可追溯，该项仍未完成。

本次实际运行 `python3 scripts/license_audit.py --help`：脚本当前不解析
命令行选项，实际执行了材料审计，报告 7 份材料通过，绑定构建
`2fc851bf0a2d1404`，证据 `build/license_report.json`。该检查核对登记文件、
哈希、SDK 副本及已构建新源码的 SPDX 标识，不是法律兼容性认证。

后续 GNU Seed 按实际链接/分发内容登记源码版本与哈希、原许可、补丁、
构建方法及对应源码材料；不能把自研默认许可套给 GNU 或 zlib。
当前 E08-2 runtime 探针在启动前返回 -2，尚未通过；binutils 交叉构建
进行中，E08-3 未验收。最新运行时工作继续记录在 0013。

本组未读取凭据、未提交/推送，未扫描或修改独立的 localpilot 项目。
