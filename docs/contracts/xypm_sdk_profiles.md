# xypm 独立运行库候选 profile

本契约规定 G4 迁移前的宿主 SDK 准入与候选生成入口。基础包容器、仓库索引、
锁文件和已安装数据库继续使用 [包计划](../plans/packages.md) 的 v1 格式；本模块
不分配 syscall、服务操作码或新的客体数据布局。现有冻结 profile 与资格记录保留。

## 运行库与安装边界

`scripts/create_xypm_profile.py` 的调用者必须显式选择 `newlib` 或 `glibc`。
候选 ID 分别以 `xos-x86_64-newlib-`、`xos-x86_64-glibc-` 开头，且创建时不能
复用 `config/package/` 中已登记的 ID。已登记候选仍可重新核验其绑定。

两套运行库使用各自完整 SDK、CRT、头文件、静态库、构建输出、仓库、锁文件及
安装盘。v1 数据库的单 profile 强校验继续生效；跨 profile 包、依赖、数据库和
仓库锁应当拒绝。同一安装盘混装需另行设计数据库/依赖/文件归属契约和客体验收。
发布者应为不同 SDK 绑定分配不同候选 ID。v1 安装数据库以 profile ID 识别目标，
完整 SDK 绑定由应用构建、检查和打包阶段核验。

`xos_app.py` 按 profile 选择应用构建后端。历史 profile 未写 `runtime_family`
时继续使用 newlib。显式 glibc profile 使用成套 glibc SDK，调用
`build_glibc_program.py` 静态编译 C 或 C++ 应用。`check` 和 `pack` 重新核对
项目、后端、SDK 和 ELF 回执。生成的 XPK 沿用 v1 格式，可以通过宿主候选盘
事务安装、升级和卸载。glibc SDK 和 profile 仍需显式选择。

## SDK 准入

所有元数据使用严格 JSON：重复键、浮点数、过深嵌套和超过 1 MiB 的文件拒绝。
元数据摘要与解析对象来自同一次读取。SDK 路径必须位于所选根内；符号链接、
特殊文件和不规范相对路径拒绝。SDK 整树摘要在检查前后核对，glibc 外部来源
核验文件也再次核对。创建的候选保存在 SDK 外，已有输出以原子排他创建方式保护。

| 内容 | newlib 候选 | glibc 候选 |
|---|---|---|
| 入口 | `--sdk` 完整发行/组合 SDK | `--sdk-build`，包含 `manifest.json` 与 `sysroot/` |
| 身份 | ABI 1、`x86_64-elf`、single、16 位小写十六进制 `build_id`、newlib 版本与头文件一致 | `static_sdk_built`、`xos_glibc_static_research_v1`、glibc 版本与头文件一致 |
| 产物 | 完整树摘要、libc/libm 元数据摘要、已有归档来源摘要 | manifest 的完整 artifact 集与 sysroot 文件集及各摘要完全一致 |
| 启动 | startup v3、`crt0_posix.o`、`user.ld` | 六个 `xos_start/crti/crtbegin/xos_start_c/crtend/crtn` 对象、`user.ld` |
| 库 | libc/libm、native SDK/loader、成套 libgcc | libc/libm/libgcc，存在的 process/terminal/unwind 库一并检查 |
| 目标格式 | 所有归档成员与 CRT 必须为 ELF64、little endian、x86-64 relocatable | 同左 |
| 来源状态 | 保留既有 `legacy_snapshot` 来源边界 | 独立 glibc 上游签名核验记录、锁、key/signature 和 gpgv 状态全部绑定 |

glibc 候选的完整身份可识别已交付但尚未写 `runtime_family` 的指定静态研究
profile；显式字段存在时必须为 `glibc`。其它 SDK 名称、相同 GCC target 或版本
字符串不能替代该身份检查。C 候选要求 G2/G3 文件操作及 pthread 创建/join
已移出 stub 清单。

默认 feature 为 `stdio`、`heap`、`file_io`、`static_tls`；C++ 和其它能力由调用者
显式选择。glibc 的 `directories`、`threads`、`spawn_delegate` 另核对应 stub
清单；出站进程能力还要求 native process 静态库和共享头。feature 是候选 SDK
接口范围，实际客体资格由对应应用/系统验收结果提供。

glibc 的 `stdio_transfer` 允许应用接收现有启动协议传入的标准文件描述符。
候选绑定包含 SDK 内的 `usr/lib/xos_stdio_receiver.o`，并校验其只读
`.xos.exec` 声明、强文件运行时引用和链接脚本保留规则。旧 SDK 缺少对象时
无法申请该 feature。构建器通过 `--stdio-transfer` 选入对象并复核最终 ELF。
`xos_app.py` 根据应用的 `required_features` 启用这一选项。

## C++ 与 unwinder

newlib C++ 使用原 single 模型、16.2.0 头文件、`x86_64-unknown-elf` 配置和独立
cpp 归档目录。组合 SDK 的 lineage 若存在，必须精确绑定 libc 与三份 C++/GCC
归档；既有完整发行 SDK 的 runtime provenance 原样绑定。

glibc C++ 要求 `cxx_runtime.status=built`、GCC 16.2.0、
`x86_64-unknown-xos`、POSIX 线程、generic locale，三条 include 目录精确匹配。
libstdc++/libsupc++ 与 libgcc 安装在 `usr/lib`，并保留 GCC 许可材料。
GCC 来源认证独立记录在 `cxx_source_verification`，其源锁位于
`usr/share/xos-glibc/cxx/port/source_lock.json`，key/signature 按锁内相对路径解析。

unwinder 必须声明 POSIX 线程、`pthread_mutex` frame registry，并逐一绑定
`unwind-dw2.o`、`unwind-dw2-fde.o`、`unwind-sjlj.o`、`unwind-c.o`、`emutls.o`
的实际归档成员摘要。前两项的 ELF 符号表还必须共同提供强未定义引用
`pthread_mutex_lock`、`pthread_mutex_unlock`、`pthread_once`；弱引用不能满足
这项约束。该 C++ 模型拒绝额外的 `libgcc_eh.a`，独立 unwind 归档须先定义其匹配
profile。这样，候选绑定可以发现归档被换回旧单线程 unwinder 的情况。

## 来源与资格

本入口检查构建器已经生成的认证材料：report 摘要与 manifest 记录、签名者指纹、
归档/源锁/key/signature 摘要、gpgv 退出状态和原始状态记录。来源状态中出现
过期、撤销、错误签名等拒绝标记时失败。SDK 树外的 report、gpgv log/status 和
keyring 也纳入绑定。真正的归档签名验证由对应 SDK 构建器执行；接手成员可从
固定源锁重新运行构建器，得到新的认证与产物证据。

候选对象记录 `sdk_binding.format_version=1`、runtime family/model、SDK manifest
与整树摘要、工具身份、链接输入、来源与可选 C++ 绑定。`verify` 根据当前完整
SDK 重建候选对象，要求规范化 JSON 全量一致；额外字段、字段删改、布尔值替代
版本整数和变更后的 SDK 都失败。

创建始终写 `status=candidate_guest_not_run`、空 `verified_system_builds`；核验
成功返回 `candidate_binding_verified` 和 `guest_qualification=not_run`。批准
新的客体资格应使用独立、可复现的实际验收记录，不通过手改生成结果增加状态。
旧 SDK、冻结 profile 和旧证据不得重新绑定到新的字节。

## 运行入口

以下环境变量由接手成员指向其已验证 SDK；输出目录独立于 SDK：

```sh
python3 scripts/create_xypm_profile.py create --runtime-family newlib \
  --sdk "$XOS_NEWLIB_SDK" --cxx --id xos-x86_64-newlib-g4-candidate-v1 \
  --output build/xypm_profiles/newlib_candidate.json
python3 scripts/create_xypm_profile.py verify --runtime-family newlib \
  --sdk "$XOS_NEWLIB_SDK" --profile build/xypm_profiles/newlib_candidate.json
python3 scripts/create_xypm_profile.py create --runtime-family glibc \
  --sdk-build "$XOS_GLIBC_SDK_BUILD" --id xos-x86_64-glibc-g4-candidate-v1 \
  --output build/xypm_profiles/glibc_candidate.json
python3 scripts/create_xypm_profile.py verify --runtime-family glibc \
  --sdk-build "$XOS_GLIBC_SDK_BUILD" --profile build/xypm_profiles/glibc_candidate.json
python3 tests/xypm_sdk_profile_host.py
```

glibc C++ 使用完成的独立 C++ SDK，创建时另加 `--cxx` 和独立候选 ID/输出。
模板、生成器和测试不改动已有 SDK，也不自动写入冻结 profile 目录。

## 静态应用构建与回退

使用与候选 SDK 绑定的工具链，选择对应的完整 SDK、候选 JSON 和独立输出目录。

```sh
python3 scripts/build_glibc_program.py \
  --sdk "$XOS_GLIBC_SDK_BUILD/sysroot" \
  --profile build/xypm_profiles/glibc_candidate.json \
  --source tests/fixtures/glibc_g2/static_main.c \
  --output build/application_glibc/static_main.elf

python3 scripts/build_glibc_program.py --cxx \
  --sdk "$XOS_GLIBC_CXX_SDK_BUILD/sysroot" \
  --profile build/xypm_profiles/glibc_cxx_candidate.json \
  --source tests/fixtures/cpp_abi/string_vector_probe.cpp \
  --output build/application_glibc/string_vector.elf
```

`--profile` 使用完整绑定核验，并在链接后再次核验。工具链对应的汇编器和链接器
按 SDK 清单校验并显式选择。头文件、CRT、libc、libm、libgcc 及 C++ 归档均来自
被核验的 sysroot。应用回执记录 profile、编译工具及 ELF 摘要，客体资格为
`not_run`。既有 C 构建入口仍接受 SDK 和源文件；`--diagnostic` 用于诊断构建。

### 独立部署 glibc 应用 SDK

`package_glibc_sdk.py` 从完整 glibc SDK 构建目录和已绑定的 profile 生成新目录。
部署目录保留 sysroot、原 manifest、glibc/GCC 来源核验文件和原 profile，并在
复制后重验整个绑定。构建源码、缓存和中间产物留在原构建目录。分发时将整个
部署目录作为一个单元，保留 `xos-app` 的执行权限。

```sh
kit="$PWD/build/xos-glibc-sdk"
project=build/hello
python3 scripts/package_glibc_sdk.py --sdk-build "$XOS_GLIBC_CXX_SDK_BUILD" \
  --profile build/xypm_profiles/glibc_cxx_candidate.json --output "$kit"
"$kit/xos-app" init "$project" --id example.hello --language cpp
"$kit/xos-app" build "$project"
"$kit/xos-app" check "$project"
"$kit/xos-app" pack "$project" --output build/hello.xpk
```

在同一配套工具链下，用该目录构建带 glibc dash 的安装候选。

```sh
python3 scripts/build_candidate.py --output build/candidates/glibc_installer \
  --glibc-app-kit "$kit" --installer-guest
```

候选清单绑定 kit、SDK、profile、dash 回执和冻结安装 ISO。
`--installer-guest` 启动实际安装 ISO，从新工作盘验收 dash 安装、首个外部 ELF
和交互命令。候选的监督进程在首个外部程序之前自动释放启动演示进程的槽位。
`--guest` 还会运行普通系统 smoke，采用仓库工具链配置中的 QEMU 版本。
系统自举和缺省的候选构建继续使用既有 SDK。切换整个应用 SDK 按迁移计划
验收存量应用和回退。
[glibc 迁移计划](../plans/glibc_port_scout.md#从加固期走向默认切换的门)

带日用工具的候选使用包含 `cxx_runtime`、`directories` 和 `stdio_transfer` 的 glibc
kit。用不同的 profile ID 发布不同的应用能力集合。`--glibc-daily-source` 接收锁定
的 sbase 源码目录，并使用同一 kit 编译、打包、绑定日用 XPK 和原生 xypm。

```sh
python3 scripts/build_candidate.py --output build/candidates/glibc_stock \
  --glibc-app-kit "$kit" --glibc-daily-source "$SBASE_SOURCE" --installer-guest
```

候选清单绑定三个安装成员。验收从空工作盘运行自动安装，重启验证文件及工具输出，
再用客体 xypm 卸载并读回非托管文件。候选生成的普通镜像仍可供独立 smoke 与回退
对照。[日用安装候选回执](../work_log/843260b2_glibc_stock_installer.md)

运行路径选中部署目录内的 SDK 和 profile，工具可随目录搬移到源树外使用。
目标构建要求 Python 3.11 及与 SDK manifest 匹配的 `x86_64-elf` 工具在 PATH 上。
编译、汇编与链接工具仍按现有规则核验。工具启动按单次调用选定运行库，切回
newlib 时重新使用冻结 SDK 的原入口、项目与工作盘。新旧盘继续遵循单 profile 规则。

发布为 glibc XPK 时，`xos_app.py` 的 `--sdk` 指向包含 `manifest.json` 和
`sysroot/` 的完整构建目录。现有项目的 `target_profile` 应与候选 ID 一致，
并使用独立项目目录。以下命令建立一个新的 C++ 应用，C 应用使用 `--language c`。
项目头文件可放在 `src/`，也可作为 `files` 的数据源登记。编译器报告的项目依赖
必须位于回执输入中，修改后应重新构建。

```sh
profile=build/xypm_profiles/glibc_cxx_candidate.json
project=build/application_glibc/hello
python3 scripts/create_xypm_profile.py create --runtime-family glibc --cxx \
  --sdk-build "$XOS_GLIBC_CXX_SDK_BUILD" --id xos-x86_64-glibc-g4-cxx-v1 \
  --output "$profile"
python3 scripts/xos_app.py --profile "$profile" init "$project" \
  --id friends.hello --language cpp
python3 scripts/xos_app.py --profile "$profile" build "$project" --sdk "$XOS_GLIBC_CXX_SDK_BUILD"
python3 scripts/xos_app.py --profile "$profile" check "$project" --sdk "$XOS_GLIBC_CXX_SDK_BUILD"
python3 scripts/xos_app.py --profile "$profile" pack "$project" --sdk "$XOS_GLIBC_CXX_SDK_BUILD" \
  --output build/application_glibc/hello.xpk
```

回退时使用原来绑定冻结 newlib SDK 的 `xos_app.json`、新旧隔离的项目输出和原
profile、工作盘。以下命令使用 `0.0.1-1024` 冻结 SDK 对应的 profile。
`XOS_NEWLIB_PROJECT` 应指向原项目或保留目标 profile 的独立副本。

```sh
python3 scripts/xos_app.py --profile config/package/xos_x86_64_static_single_v1.json \
  build "$XOS_NEWLIB_PROJECT" --sdk "$XOS_FROZEN_NEWLIB_SDK"
python3 scripts/xos_app.py --profile config/package/xos_x86_64_static_single_v1.json \
  check "$XOS_NEWLIB_PROJECT" --sdk "$XOS_FROZEN_NEWLIB_SDK"
```

### 工作区的应用 SDK 默认选择

`scripts/xos_sdk.py` 为应用开发和宿主包工具保存同一选择。初始化时验证已部署的
glibc C/C++ kit 和 1024 发行冻结 newlib SDK，并将 glibc 设为该工作区的默认值。
选择保存在本地 `build/application_sdk_selection.json`，`--state` 可显式使用另一份
选择文件。每项选择都绑定 SDK 树、manifest 和 profile。应用工具继续验证工程的
`target_profile`，包工具将选择的 profile 交给既有 XPK、仓库锁和工作盘检查。

```sh
python3 scripts/xos_sdk.py setup --glibc-kit "$GLIBC_KIT" --newlib-sdk "$FROZEN_NEWLIB_SDK"
python3 scripts/xos_sdk.py status
python3 scripts/xos_sdk.py app init build/example --id example.hello --language cpp
python3 scripts/xos_sdk.py app build build/example
python3 scripts/xos_sdk.py app pack build/example --output build/example.xpk
python3 scripts/xos_sdk.py xypm verify build/example.xpk
```

切回冻结 newlib 时运行 `python3 scripts/xos_sdk.py use newlib`，再对原工程和
原工作盘使用同一入口。`use glibc` 恢复 glibc 的选择。切换只原子替换选择文件。
选择的套件缺失或摘要变化时命令报告错误。切回 newlib 只需要原 newlib SDK 与
profile 可用。两种选择均要求操作者为包事务显式指定输入和输出盘，现有工程、
数据库和包归属沿单 profile 规则。需要不同绑定时初始化独立的选择文件。

默认入口只在已有对应 profile 的工作盘上运行查询与事务。未登记的工作盘无法仅
从缺少数据库确定其 ABI。第一次安装时用新建的专用盘，并由既有 `xypm.py` 的
显式 `--profile` 入口生成初始数据库，之后可继续通过默认入口处理该盘。

```sh
python3 scripts/xypm.py install build/example.xpk --offline --profile "$GLIBC_KIT/profile.json" \
  --image "$blank" --output-image "$glibc_work"
python3 scripts/xos_sdk.py xypm verify-installed --image "$glibc_work"
```

该入口的默认作用域是已配置工作区的应用与宿主包命令。安装候选、系统自举、原
显式工具入口与发布材料仍采用独立的既有路径。整个 SDK 的发行默认项、生产许可
及 newlib 退役继续使用发布门。[发布手册](../releases/playbook.md#glibc-应用-sdk-发布预览)
