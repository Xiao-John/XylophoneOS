# 已发布版本与下一次发行准备

2026-10-26。**0.0.1-1026已发布**；本页不再把该版本的冻结、打包、源码材料或
工作盘预装决策列为待办。后续本地改动尚未发行，不改写旧资产或验收结果。

## 0.0.1-1026冻结回执

- 标签`v0.0.1-1026`、源码提交`db5b46cf36b57a602946a370269563f9c8dd212f`。
- build`7a4668477d7323de`，release smoke 11/11，资源[130272,2,0]；
  7份许可材料检查通过，newlib成员级追溯仍开放。
- 新工作盘不预装dash；install ISO携带dash并在首次启动安装，已存在文件不覆盖。
- images/SDK/source/校验表/manifest均已上传，来源与哈希见
  [发布回执](release_0_0_1_1026.json)及[0050过程记录](../history/delivery_audit.md#log-0050_release_candidate)。
- 容量probe kernel和附加trailer的dash仅用于0047验收，不是发行载荷。

| 已发布资产 | SHA256 |
|---|---|
| CHECKSUMS.sha256 | `e65457ba52f40d23ff602ebf3e53479a614c51a3c95f8e580d4c607392f15848` |
| release_manifest.json | `6d73a563b9ae7089e324e381dc912223a5103897d88230ff79948159cb8051d6` |
| xos-0.0.1-1026-sources.tar.gz | `3f1ead9867ca567a3a1e14edd59fcbca42d238b9159c115fc96b9e7727930657` |
| xylophoneos_revival_0.0.1-1026_images.tar.gz | `8dcc344f5126c2128896684455116d288d8331ca08f5d16118bf72abf7d131a8` |
| xylophoneos_revival_0.0.1-1026_sdk.tar.gz | `a09e6157fc5409152e2646484eb03cec5509433558734fb921d161c53365b4a1` |

## 下一次发行时的工作

1. 另选新版本目录，冻结届时系统、SDK、运行库、应用与源码提交，禁止覆盖1026资产。
2. 按实际变更选择定向gate；旧报告只追溯原快照，不能直接改绑新源码或重写失败。
3. 0054起打包器要求SDK精确文件/目录集合、manifest、build/config与运行库来源绑定；
   记录到发行manifest，资格报告核对同一输入。旧1026回执缺此字段仍保留历史原样。
4. 生成对应新源码材料及许可声明，发布文案保持简洁，工程证据另存manifest/工作记录。

本轮审计修复不生成或发布新版本，也不因材料检查通过声称成员级法律审计完成。
