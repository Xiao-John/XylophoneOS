# glibc 统一发行入口与冻结回退

`scripts/release_pipeline.sh` 的默认流程为 glibc。它要求调用者提供实际候选、
应用 kit、包和回执；缺失输入直接失败。历史 newlib 流程保留为
`scripts/release_pipeline.sh --newlib STAGE`。这项命令默认值不修改已发布版本，
也不代替 [默认发行验收表](glibc_default_gate.md) 的最终组合资格。

开发环境使用已校验的 pre-release SDK Preview 2 Linux x86-64。其宿主工具可
用于本流程，但附带的 **newlib sysroot 不是 glibc 应用 kit**。glibc kit、
冻结 newlib SDK 和各自工作盘必须分别绑定。不得将 Preview 2 的 newlib sysroot
重命名为已验收的 glibc kit 或 v0.0.1-1024 回退 SDK。

## 阶段

| 命令 | 实际工作和失败边界 |
| --- | --- |
| `build` | 调用 `build_candidate.py`，要求独立候选输出、glibc kit 和日用工具源；强制运行普通及安装客体 gate。 |
| `package` | 调用 `package_release.py` 的 glibc 分支，验证安装候选、SDK/profile、daily、CPython/zlib 及可选 IDNA/GNU Seed；历史参数不能隐式进入 newlib。 |
| `smoke` | 对显式 `--glibc-release` 和新的 `--output` 运行现有包与 GNU Seed 客体；保留原来的 `passed_subset` 范围。 |
| `components` | 调用 `package_glibc_release_sources.py build/verify` 收集或验证对应组件源码。 |
| `materials` | 调用 `stage_glibc_release_supplements.py`，要求 glibc 源、xypm、Dash、日用工具、GNU Make 和 CPython 的实际重链材料。 |
| `gates` | 要求显式 `--build` 的 manifest 与发行 system manifest 摘要一致，然后扫描该构建的许可材料；不声称已运行新的客体。 |
| `freeze` / `checksums` | 将同一候选的基础归档、完整 v6 补充材料、包/GNU 客体回执和 SDK 回退绑定校验后复制到一个新目录；只产生 `assembled_static_distribution`。 |
| `status` | 重新验证候选实际产物并显示构建和 SDK 身份。 |
| `sdk` | 复用 `xos_sdk.py` 管理两套 SDK 的绑定、应用和包工具。 |
| `rollback` | 显式选择已绑定的冻结 newlib SDK；不改两套工作盘。 |

`application-preview` 保留原先的独立预览命令。每个阶段的准确参数可通过
`scripts/release_pipeline.sh STAGE --help` 查看。参数通过 argv 传递，不解释
shell 内容。原 `package --glibc-candidate ...` 和 `smoke --glibc-release ...`
调用保持兼容。

## 使用顺序

以下变量指向操作者提供的真实输入。`KIT` 是已验收的 glibc 应用 kit，
`FROZEN_NEWLIB_SDK` 是有历史绑定的 v0.0.1-1024 SDK；`CANDIDATE`、`RELEASE`、
`SMOKE` 和 `DISTRIBUTION` 选择不同的新输出目录。

```sh
scripts/release_pipeline.sh sdk --state "$SDK_STATE" setup \
  --glibc-kit "$KIT" --newlib-sdk "$FROZEN_NEWLIB_SDK"

scripts/release_pipeline.sh build --output "$CANDIDATE" \
  --glibc-app-kit "$KIT" --glibc-daily-source "$SBASE"

scripts/release_pipeline.sh package --release-dir "$RELEASE" \
  --glibc-candidate "$CANDIDATE" --glibc-app-kit "$KIT" \
  --cpython-package "$CPYTHON" --wheel-package "$IDNA" \
  --gnu-seed-donor "$SEED" --gnu-make-receipt "$MAKE_RECEIPT" \
  --gnu-make-sources "$MAKE_SOURCES"

scripts/release_pipeline.sh smoke --glibc-release "$RELEASE" --output "$SMOKE"
```

按 `components`、`materials` 的参数收集匹配材料后，`SUPPLEMENTS` 必须包含
完整 `xos_glibc_release_supplements_v6` 回执、glibc 上游源和全部对应重链归档。
只提供 xypm 的旧 v1 补充材料不能通过最终收拢。

```sh
scripts/release_pipeline.sh freeze --release "$RELEASE" \
  --supplements "$SUPPLEMENTS" --smoke "$SMOKE" --sdk-state "$SDK_STATE" \
  --output "$DISTRIBUTION"

scripts/release_pipeline.sh rollback --state "$SDK_STATE"
scripts/release_pipeline.sh sdk --state "$SDK_STATE" use glibc
```

冻结目录包含基础 4 份归档、对应源和重链材料、实际回执、无宿主绝对 SDK 路径的
`pipeline_receipt.json` 与覆盖全部交付文件的 `CHECKSUMS.sha256`。冻结使用
Linux `renameat2(RENAME_NOREPLACE)`；已有输出或冻结期间新出现的同名目录都
不覆盖。复制阶段发现输入变化时，临时目录回收且目标目录不出现。

## 资格边界

此入口将现有实际校验器组成可执行流程，不把元数据检查或宿主文件事务测试记为
新的客体通过。`freeze` 要求包烟测和原生 GNU 烟测都绑定同一 release manifest、
工作盘、ISO 和 profile；合并回执还必须绑定原始两份报告。报告中的
`passed_subset` 保持原样。SDK 回退绑定表明实际旧 SDK 仍可验证，不等于重新
冷启验收过最终发行与旧工作盘的往返。

公开动态应用启动、D3 激活代际、多程序 D4 组合、断电语义及入选应用的完整发行
资格仍须按各自契约完成。所有缺口在回执中列为未取得资格，不由默认命令路径
自动消失。发布 tag、上传 release 和合入代码沿用操作者的明确授权。
