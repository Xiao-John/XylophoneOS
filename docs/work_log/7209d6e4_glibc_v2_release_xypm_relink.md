# 7209d6e4 · glibc v2 发行版 xypm 静态复链

本轮选择统一 C/C++ v2 候选的实际发行程序 `/usr/bin/xypm`。发行清单绑定
候选 stock 回执，五个 C++ 翻译单元按回执绑定的项目输入重编。目标 ELF 与
发行安装器写入测试工作盘的程序逐字节一致，SHA-256 为
`c2511d6702557e213cd181b8bd5c35a40fd5f2fe4356404b284d0ac442c0e745`。

## 独立接收和替换

本地材料目录共 58 个登记文件、40,734,322 字节，含五个应用对象、对应源码、
实际链接顺序与输入、许可证文本、SDK 和发行回执及独立复链入口。断网 Linux
接收容器只挂载材料目录、替换归档及新的输出目录，使用回执绑定的 GCC 16.2.0
和 Binutils 2.47。原库复链得到发行 ELF。错误材料清单摘要和错误替换归档摘要均
在产生输出前拒绝。

替换试验从签名 glibc 2.44 构建树核对 `ioputs.o` 和 v2 `libc.a` 中成员的
一致性。使用原 `make-lib.log` 内该翻译单元的目标编译命令、同一构建目录和
工具链，只把输入和输出指向私有副本，并应用
[`xypm_libc_version.patch`](../../tests/fixtures/glibc_g4/xypm_libc_version.patch)。
以目标 `ar rD` 把新成员写入 `libc.a` 副本。对两份归档按顺序逐成员读取，
1,686 个成员中只有 `ioputs.o` 的内容摘要变化。替换版 ELF 为
`37d2a4b5540ea06672aafe4ce55f79266662f52fb142ba2f40e06ff50b78c622`。
诊断标记只在该试验库收到确切的 xypm 版本字符串时出现。

## 原生客体

在普通发行镜像 `ce681c073de3d6c4` 的 QEMU 11.1.3 上，原版和替换版各执行
`--version` 与 `list`，四次均退出 0。原版报告既有版本，替换版额外显示
`[REPLACED_LIBC]`，两份程序均报告新盘暂无已安装包。每次恢复
`129806 / 2 / 0` 的资源基线，停机后 FAT 盘中的两个 ELF 保持原字节。
首次客体命令误用了小于测试工具下限的 FAT32 尺寸。修正为 512 MiB 稀疏临时盘
后完成复验并自动回收该盘。链接器报告现有 `raise` 占位告警，本次未覆盖信号。
[绑定回执](../reports/glibc_v2_release_xypm_relink_20261127/manifest.json)

## 复跑

用已冻结的发行 SDK 和已发布 xypm 项目回执。将回执 `inputs` 映射保存为独立
JSON，从该快照根按原 `xos_app.json` 的五项 `sources` 顺序运行
`scripts/build_glibc_program.py --cxx --stdio-transfer`，传入同一 profile、
`--project-inputs`、`--include-dir src` 和候选 sysroot，保留 ELF 旁
`.build` 目录。然后在相同构建环境执行以下命令。

```sh
python3 -B tests/glibc_release_xypm_relink.py collect \
  --release "$RELEASE" --candidate "$CANDIDATE" --project "$FROZEN_XYPM_PROJECT" \
  --reference "$REBUILT_XYPM" --output "$MATERIALS"
python3 -B "$MATERIALS/tools/relink_release_xypm.py" --materials "$MATERIALS" \
  --sha256 "$MATERIALS_MANIFEST_SHA256" --output "$ORIGINAL"
python3 -B "$MATERIALS/tools/relink_release_xypm.py" --materials "$MATERIALS" \
  --sha256 "$MATERIALS_MANIFEST_SHA256" --output "$VARIANT" \
  --libc "$REPLACEMENT_LIBC" --libc-sha256 "$REPLACEMENT_LIBC_SHA256"
python3 -B tests/glibc_release_xypm_relink.py guest --release "$RELEASE" \
  --original "$ORIGINAL" --replacement "$VARIANT" --installed-disk "$INSTALLER_GUEST_DISK" \
  --installed-disk-sha256 "$INSTALLER_GUEST_DISK_SHA256" --output "$GUEST_REPORT"
```

接收材料可与已冻结 v2 工具包及其对应源码核验记录成套使用。这里覆盖实际发行
的一个 C++ 程序与诊断替换库。其他随包程序的对应源码、成员级材料和接收方
客体仍需逐项补齐。默认 SDK 切换依照独立发行门。
