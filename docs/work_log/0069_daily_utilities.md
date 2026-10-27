# 0069：日常工具 DU1/DU2 初步实现

2026-10-27。依用户指定的 `/Users/xylo/Documents/XylophoneOS/docs/plans/daily_utilities.md`
实施；该设计位于其他工作区且当时尚未提交。本工作区未修改或提交该工作区内容。

在 `src/ports/sbase/xos/` 实现独立 `ls`、`rmdir`、`head`、`tail`、`wc`、`tee`、
`basename`、`dirname`，并修订已有 `cat`、`cp`、`mv`、`rm`、`mkdir`。新增
`src/ports/sbase/daily_utilities.json` 和 `scripts/build_daily_utilities.py` 统一声明
工具与构建回执；旧五工具的构建脚本不覆盖。新代码 Apache-2.0；旧 sbase 派生部分
保留 MIT 并标记新修改。新增客体测试及脚本，但此时尚未运行。

初次构建 `python3 scripts/build_daily_utilities.py --sdk build/utf8_filenames_qualified/sdk
--source /Users/xylo/Documents/XylophoneOS/.cache/xos_seed/sbase/repo --output-dir
build/daily_utilities_du12` 13 个 ELF 成功；该构建在最终许可证标识/清单调整前，不能
作为最终源码回执，须重新构建。未执行系统构建、客体运行、管道/文件错误验收、
许可证审计或 xypm/ISO 安装；所有候选为 built_not_run，尚不能宣布 DU1/DU2 已完成。

## 提交后定向验证

源码 `a25b3cd`、系统 build `0b7cdbfda763d948`，镜像 SHA256
`a45d868fa32ab06723c67eb7cb7a90d3dcbf3eb4caca8c8f963a19303ac0f461`；
工具清单 SHA256 `c427ec68dafc1184f68708c1c7c12420b16b562e761acc0ba23d81305345176c`。
`scripts/build_daily_utilities.py` 使用该系统 SDK 重建 13 个 ELF；
`tests/daily_utilities_smoke.py` 在专用盘用 dash C3（SHA256
`9fdd8b45e065f6756f21a264ea642744ea8675cff84194a5090335fbec57fd59`）验证
13 个工具组成的基本命令链、管道、部分错误和结果字节，以及 xsh 显式调用 ls，通过。
资格仅限这些输入；单独 13 项完整支持面、所有失败模式及资源回收未通过完整 gate。
首次错误选用 dash A，因重定向不可用失败；换用 C3 后通过，不改写早期失败报告。
许可材料检查及 ABI 文档检查通过；未做逐成员法律审计。

下一步补充
各工具的选项/错误/大输入/资源回收及 xsh/dash/UTF-8 路径边界。DU3、工具包 profile、
发行路径和空盘 ISO 完整安装均未实施；xypm P2 另行完成并验收，不能把旧资格改绑。
