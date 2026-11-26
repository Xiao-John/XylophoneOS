# 907ccb19 · glibc 日用工具 XPK

沿用 v1 包、文件归属和事务格式。glibc XPK 使用完整的 SDK 构建目录和显式
候选 profile。打包器核对工具清单、完整 SDK、profile、接收对象和每个 ELF 的
摘要。日用工具与普通应用复用同一个 SDK 许可材料选择入口。newlib 对照用相同
SDK、profile 和工具回执分别走旧、新打包器，得到逐字节相同的包。
打包时检验实际进入暂存目录的 ELF 字节，并将每份 SDK 许可材料的内容
与已绑定清单核对。重新生成的 glibc 和 newlib 包均保持原先的对照摘要。

`stdio_transfer` 候选绑定包含已构建的 `xos_stdio_receiver.o`。接收对象提供
强文件运行时引用和只读 `.xos.exec` 声明。工具链接后再次校验该声明。
老版本构建的同一 glibc 2.44 SDK 因缺少对象而拒绝。将相同版本 SDK 的
`crti.o` 替换到接收者路径并重新计算 artifact 摘要时，候选仍因缺少声明而拒绝。
普通 `xos_app` C 构建的 `required_features` 可显式选择同一对象。
[候选绑定契约](../contracts/xypm_sdk_profiles.md)

| 验证输入 | SHA-256 |
| --- | --- |
| 正常系统 `5188c778d6ea0856` ISO | `9ae877f92b1c5b0fc2cffa3de1e6bc20b19a84b9c5b6b99d3566fbf3eb300bd8` |
| 最终复验系统 `4de48be046f61008` ISO | `436bbb137475ea32ebed4298b4f7950cbb32f4ff8bdbd08caa7f70bedfdf2f6c` |
| 签名核验的 glibc C SDK manifest | `c31e829280dcfb4c3d0abf549b6e55298c4384460a2f2da3de309192aa1226d2` |
| C SDK 压缩包 | `4664a14e95b2ddbe9e5ad9430ee3ebe06d883bd3034acc374a5c05897f42d695` |
| 候选 profile | `cdbab89c9f6fa463aaf5e65d4dac5db33ccf339db79ebb626d0ed7fc2d209782` |
| SDK 接收对象 | `b16a63ed21dc545b42e4711febf359efc166d51d07240b561705c1a788c67f58` |
| 13 工具构建回执 | `5871b98ab1324f7c592fe61de2c3e81056928643f6e5900931dac81a99b5d023` |
| glibc dash ELF | `3bed784c4b30b8bc578938b8100d1192e7dbf020573efad8a86685fe4f9613eb` |
| glibc 日用工具 XPK | `986013b1f068450d96c9f2135052c3549aa09b446cf3422fcd7510b9f8eb628f` |
| newlib 两打包器对照 XPK | `ecadaad4e4d85790c3c5eb8d0fc63caf4823ab83baea43ea424a90710fce21e8` |
| 最终 XPK 生命周期回执 | `66f95d0305d3b4de375a91e60158f419c095244c29fb8483727000bc315c0ea3` |

宿主 profile 套件 45 项通过。明示选择 newlib profile 时，现有包核验入口拒绝
glibc 包的目标 ID。glibc XPK 容器为 38,215,680 字节，含 26 个 payload 文件。

宿主 v1 事务从 XPK 安装到独立 FAT 磁盘，QEMU 使用该盘运行原 `du12.sh`。
随后同步用户输出，按包清单读取全部已安装文件，并运行宿主卸载事务确认用户
数据仍保留。测试的脚本等待预算显式设为 480 秒，默认仍为 180 秒。
[包生命周期门禁](../../tests/daily_utilities_package_smoke.py)

QEMU 11.1.3 的最终复验六项通过。损坏包及与用户文件冲突的安装被拒绝，
冲突时原盘摘要保持一致。安装的 26 份文件经摘要复核，卸载后已安装包记录
为空，用户工作目录中的管线结果仍为预期字节。

## 默认交付边界

原生 `xypm` 在构建时绑定包目标 ID，并在包、仓库和已安装数据库维持同一
profile。当前构建入口使用同一 profile 选择管理器的编译 SDK 和包准入。
本次包的 C SDK 资格覆盖工具与宿主 FAT 候选盘事务。客体内 P2 维护需要
匹配该包 profile 的管理器构建及单独的真实客体回执。普通系统 SDK、自动
安装路由以及完整 C3 shell 能力仍是默认迁移的独立门禁。
[管理器构建入口](../../scripts/build_xypm.py) · [原生包校验](../../src/user/programs/xypm_native.hpp)

将当前 dash 和 XPK 同时放入安装 ISO 时，实际 bundle 为 41,592,668 字节，
现有 33,554,432 字节限额会拒绝该组合。FAT 安装路径可单独消费此 XPK。
[镜像包装入口](../../scripts/build_install_iso.py) · [v1 bundle 限额](../../scripts/xos_bundle.py)
