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

随后针对 `cp`、`rm` 的文件检查失败采取保守处理，补管道输入、无末尾换行、追加、
无效选项探针；提交 `194b67e` 的最终重建 build `0babbb11032c9197`，镜像 SHA256
`d133880420f374a326438c898111f45a6c44c7fc9a26f5c390016baeb57bd1db`；
工具清单 SHA256 `d0b47ac72d1d8a508d042684f8261443bb3610a1a923b6fcc301e8564203b421`。
同一专用盘的扩充命令链、xsh 显式执行与逐字节输出通过；报告位于
`build/daily_utilities_system_v4/du12_report.json`。文档/ABI一致性、7份许可材料检查
通过，逐成员审计仍未完成；完整逐命令资格仍未通过。

下一步补充
各工具的选项/错误/大输入/资源回收及 xsh/dash/UTF-8 路径边界。DU3、工具包 profile、
发行路径和空盘 ISO 完整安装均未实施；xypm P2 另行完成并验收，不能把旧资格改绑。

2026-10-28：增加 `config/package/xos_x86_64_daily_c3_candidate_v1.json` 和
`scripts/package_daily_utilities.py`，用于绑定 0babbb11032c9197 的实际 SDK 树、13 个
ELF 和材料生成离线候选 XPK。此 profile 仅记录已跑过的受限命令链，不是已冻结的发行
profile 或完整工具资格；包安装、旧 profile 拒绝和客体检查待提交后运行。

## 2026-10-28：候选包与 P2 组合

- 先以旧组合 `0babbb11032c9197` 生成 `xos.daily_utilities` 候选包；旧 B2 profile
  因不匹配拒绝。专盘离线安装、客体命令链、卸载及用户文件保留通过；损坏包与已有
  未托管 `/usr/bin/ls` 拒绝，源盘摘要不变。
- 在本分支合入 `d6363f8` 的 xypm P2，组合系统 build `35881bb342b35a3e`、镜像
  SHA256 `37b72ac21a669348609d497c9ae058a05395149edfb454e729ac590bc40ada18`。
  合成 SDK tree `9193cd1ded75abc826138b121e8970500b20e2fc4f62465e816be9b3d43e2b08`，
  使用新 profile 重建 xypm 和 13 个工具，候选 XPK SHA256
  `aea8f71b243a6047e94227b518409b76ed0b68614e6b2fabd57e7de5eb854699`。
  P2组合事务 8 项通过；宿主/客体 21 个包样本和计划/错误路径比较通过，报告分别在
  `build/daily_utilities_p2_transactions/` 和 `build/daily_utilities_p2_verify/`。
- 实际工具 XPK 经客体 P2 `maint-run` 安装、重启后执行包含二进制 NUL/管道的命令链，
  客体卸载并保留用户文件，安装/执行/卸载资源回到基线；
  `build/daily_utilities_p2_guest_v2/report.json`。此前 P2 大规模故障检查资格未改绑。
- `scripts/prepare_daily_sdk.py` 可按系统产物和已登记 B2 C++ SDK 重现组合 SDK 与候选
  profile；`scripts/package_release.py` 增加显式候选包/profile/SDK入口并校验文件冲突、
  profile、构建回执、系统 SDK 和 C++ 运行库。预检覆盖有效输入、错误系统/SDK、
  未托管冲突和不兼容 wheel profile；未实际打出发行或修改既有发行资产。
- 新增客体测试文件和打包脚本在组合系统构建后提交；因此上述证据严格绑定该系统镜像、
  SDK、实际包和测试输入，不宣称当前完整源码清单的最终系统重建资格。坏盘、断电、
  安装中断、实际升级、大文件和全部命令选项仍需补测。ISO 通用载荷及空盘安装未实施，
  DU3 尚未开始；不能说“启动 ISO 已获得工具集”。
