# 0051：xypm P2-2客体校验与只读计划（实现初版）

日期：2026-10-26。接续0048的P2-1维护门控，实现P2-2的只读部分。本记录不是P2-2
验收通过声明：客体执行和共享畸形输入夹具均未运行，P2-2仍进行中。

## 范围与行为

- `xypm verify <package.xpk> [sha256]`：对同一只读打开文件流式读取；限制包总长、
  ustar成员/类型/校验和/填充、manifest长度与JSON深度；检查严格UTF-8/重复键/整数、
  v1字段、受限路径、编译profile/features、manifest与payload成员集合，以及manifest
  所列每个payload SHA-256。可选参数校验调用方预期整包摘要。
- `xypm plan install|upgrade <package.xpk>`：先完成包校验，再只读校验安装数据库和
  `index.tsv`摘要绑定、profile、精确依赖与依赖环、所有权、已安装文件大小/摘要、目标
  父项和FAT目录项返回的规范名；最后打印计划摘要。此命令不创建目录、不写数据库/包文件、
  不执行包内程序或授予构造权。
- `scripts/build_xypm.py`现在将校验器和按冻结profile生成的feature表纳入缓存键与包源码。
  新自研头文件标记Apache-2.0；无第三方依赖、无公共ABI/内核修改。

## 约束与未完成

- guest现有数据库最多64包、8192归属文件、数据库/index各1 MiB；manifest 1 MiB、最多
  8192成员、单文件64 MiB、payload 256 MiB，JSON深度8/每份JSON最多8 MiB解析arena。
- guest尚未复制宿主的完整ELF PT_LOAD布局检查；guest包解析与宿主 `verify_package`
  的恶意/边界样本一致性尚未建立。SHA-256匹配只表明内容与包声明相符，不验证发布者。
- 没有安装、升级、卸载、journal、备份、恢复命令。P2-3和P2-4未开始。

## 构建与证据

使用profile `xos-x86_64-static-single-b2-v1`和已登记冻结SDK
`.cache/xos_seed/xypm_sdk/single_b2_v1`。第一次误用0.0.1-1026发行SDK时被
`xos_app.sdk_check`拒绝，因为其树摘要未登记为B2单线程profile；没有更改profile或SDK。
随后使用冻结B2 SDK成功执行：

```sh
python3 scripts/build_xypm.py --sdk .cache/xos_seed/xypm_sdk/single_b2_v1 --profile config/package/xos_x86_64_static_single_b2_v1.json
git diff --check
```

成功打包的缓存构建键为`82ce48cca0ac766f7540`；ELF约844 KiB，XPK约1.5 MiB，含36个
文件，包SHA-256为`3bfe31d409be4ffa079260779ccf36f3feef9c32ea62f97a1d17f77cc3d16434`。
ELF最大可写段含约4 MiB BSS；两份各8 MiB的JSON解析arena按需从进程堆分配。生成回执状态为
`packed_guest_not_run`。`git diff --check`退出0。

未运行：xypm客体命令、host/guest共享畸形XPK和数据库夹具、维护worker计划入口、完整系统
构建、许可审计。故不报告任何guest通过率、资源基线或P2-2完成。

## 下一步

先补与`scripts/xypm_format.py`、`scripts/xypm_image.py`共享的有效/畸形样本及guest runner，
在隔离工作盘中执行verify/plan安装与升级、损坏数据库、路径别名/父项冲突、精确依赖、
截断/重复/损坏哈希等检查；补齐或明确guest ELF检查契约差异后再关闭P2-2。其后才进入
P2-3持久intent/staging/backup与启动恢复门禁。
