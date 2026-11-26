# cc71c241 · glibc stock 安装盘的应用组合

以 `843260b2` 构建的 stock 安装候选 `7f88e4f9070640c2` 为输入。将安装镜像、同一
系统版本的普通启动镜像、XOSBND1 的安装回执及 stock SDK 复制到独立工作区。用
`xos-x86_64-glibc-stock-v1` 在断网 Linux arm64 容器重建两个外部应用，并以 SDK
自身的 `xos-app build`、`check`、`pack` 生成 C 和 C++ XPK。GNU Make 4.4.1 从
锁定源码归档重建，`gpgv` 核对了项目固定的主密钥指纹和对应的分离签名。该签名生成于
2023 年，验证时密钥已到期。三份构建回执均对应候选的 profile、SDK 清单和完整 SDK 树。

组合测试在同一张新 FAT 工作盘先通过离线 xypm 安装 C 和 C++ XPK，导入 GNU Make
ELF。第一次真实 QEMU 启动由 stock 安装器自动加入日用工具包。第二次用同一内核构建的
普通 ISO 启动同一张盘。脚本验证 C 运行时和原用户数据、C++ 线程及异常、GNU Make
直接和 shell 配方，以及日用 `cp` 和 `cat`。第二次启动读取第一次由 `cp` 产生的文件。
两次停机后使用离线 xypm 核对包身份及全部已登记文件，最后从 FAT 逐项导出核对 dash、
GNU Make 和两个状态文件。dash 核对 XOSBND1 的 ELF 成员摘要。

QEMU 11.1.2 两次均通过。每次停机后的包库均含三个包和 50 个已验证文件，四个最终导出
文件的摘要均符合预期。启动阶段自动退休的演示任务有完整回收记录，其余任务与内存资源
恢复到基线。既有未打包 dash 候选 `e6a349fa12ec0a89` 也用本 runner 通过两次实体
启动及 FAT 读回。profile 宿主测试 45 项通过。
[组合回执及复现用应用源码](../reports/glibc_stock_apps_20261126/manifest.json)

首轮测试 `7a9df205` 在 C、C++、GNU Make 和 `cp` 运行后执行 `$(cat …)`，
真实 dash 按预览契约拒绝命令替换并退出 2，第二次启动未执行。该首次失败的串口单独保留。
复测直接校验 `cat` 的实际串口输出及同一文件的 FAT 读回，命令替换仍须单独验收。

从冻结的候选、SDK 和签名源码重放，在 Linux 构建环境运行下列命令。源码目录为组合回执
随附的 `external.c` 和 `external.cpp` 所在目录。所有应用构建输出和客体回执使用独立输出路径。

```sh
for language in c cpp; do
  project="$BUILD_ROOT/app-$language"
  "$SDK_KIT/xos-app" init "$project" --language "$language" --id "selection.kit_$language"
  cp "$FIXTURES/external.$language" "$project/src/main.$language"
  "$SDK_KIT/xos-app" build "$project"
  "$SDK_KIT/xos-app" check "$project"
  "$SDK_KIT/xos-app" pack "$project" --output "$BUILD_ROOT/external-$language.xpk"
done
python3 scripts/build_gnu_make.py --sdk "$SDK_KIT/sdk" --profile "$SDK_KIT/profile.json" \
  --archive "$GNU_MAKE_ARCHIVE" --signature "$GNU_MAKE_SIGNATURE" \
  --keyring "$GNU_KEYRING" --output-dir "$BUILD_ROOT/gnu-make"
python3 tests/glibc_selected_app_matrix_guest.py --candidate "$CANDIDATE" --sdk-kit "$SDK_KIT" \
  --c-xpk "$BUILD_ROOT/external-c.xpk" --cxx-xpk "$BUILD_ROOT/external-cpp.xpk" \
  --make-manifest "$BUILD_ROOT/gnu-make/manifest.json" --output "$OUTPUT"
```

覆盖范围是静态 glibc 应用、离线安装的两个外部 XPK 和客体安装的日用工具包。
GNU Make 仍以 ELF 导入。动态链接、GNU Make 递归 jobserver、其他存量包、SDK 默认
入口及 newlib 退役须各自验收。

新候选完成安装器验收后，以其冻结清单、两张 ISO 和同一清单绑定的应用 kit 重新跑组合。
若候选使用不同的 SDK 树、SDK 清单或 profile，按上述命令重建两个 XPK 和 GNU Make。
新的报告同时记录新候选清单、两张 ISO、三个包和 GNU Make 的摘要，以及该次真实客体
结果。此处保留候选 `7f88e4f9070640c2` 的原始阶段证据。

## 安装回执加强后的两次启动

候选 `7ec6c8d583db12c9` 已完成两张 ISO 与 SDK 回执交叉核对。旧应用的完整 SDK 树和
profile 摘要与新候选相同，可以复用原应用字节。真实 QEMU 以新安装镜像及普通镜像
启动同一工作盘，重复通过 C、C++、GNU Make、日用工具和状态文件持久化。每次停机均
核对三个包、50 个登记文件，最终 FAT 读回四份文件。两张镜像及 runner 的摘要重新绑定。
[新候选组合回执](../reports/glibc_stock_apps_post285_20261126/manifest.json)
