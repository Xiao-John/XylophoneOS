# b0a92aab · glibc v2 安装器 Dash 接收复验

以 [v2 组件对应材料](9c747f60_glibc_v2_component_sources.md) 和已验收发行
清单为输入。断网 Linux 容器从补充归档还原 Dash 的锁、上游原件、补丁和
XOS 桥接源码，用同发行只读应用 SDK 在空构建缓存中运行 `build_dash.py`。
重建 ELF 为 3,315,096 字节。该 ELF 和构建回执与发行时逐字节一致，回执记载的
1,837 项输入与冻结回执全部相同。环境使用 GCC 16.2.0 的宿主 `cc` 和 v2
绑定的交叉工具。初次环境预检要求了容器中缺少的 clang，正式配方的宿主 `cc`
回退随后通过。

直接用 xorriso 从冻结 ISO 提取 `DASH.ELF`，用 `xos_bundle.py verify` 核验
XOSBND1 的全部成员，再取类型 1、名称为 `dash` 的字节区间与新 ELF 比对。
容器大小为 15,913,256 字节，Dash 位于偏移 272，SHA-256 为
`f30495d9229d1550bc01b6c6cfb199924058e129d845a6a50c3d303f69e1243a`。
构建与容器摘要收录在[字节比对回执](../reports/glibc_v2_dash_receiver_20261127/byte_compare.json)。

同一冻结安装 ISO 用 QEMU 11.1.3 和新的 512 MiB 稀疏 FAT32 盘执行
`tests/iso_dash_install.py --external`，5 项检查全部通过。安装后的命令解析到
`/usr/bin/dash`，运行外部 ELF 后打印 `A3EXTERNAL` 并以 0 退出。交互测试打印
`A3DASH` 并以 0 退出。两次看到的提示符和退出信息可在原始串口记录中复核。
[客体回执](../reports/glibc_v2_dash_receiver_20261127/installer_guest.json)

## 复跑

在与生产目录隔离、禁用网络的 Linux 环境中，将 `MATERIALS`、`SDK` 和冻结
ISO 以只读方式提供给接收方。使用与 `b0a92aab` 相同的脚本和配置。
以下命令在新的接收目录内执行，`SDK` 指该发行的 `application-sdk`。

```sh
git -C "$XOS" archive b0a92aab scripts config VERSION | tar -xf -
python3 -B scripts/package_glibc_release_sources.py verify \
  --archive "$MATERIALS/component-sources.tar.gz" \
  --manifest "$MATERIALS/component-sources.json" \
  --manifest-sha256 80048e009ea761149f8e416f35502891d20fdec737dedffcb24adcfd8df47f01
tar -xzf "$MATERIALS/component-sources.tar.gz" --strip-components=2 \
  xos/candidate/src xos/candidate/scripts/build_dash.py
python3 -B scripts/build_dash.py --sdk "$SDK/sdk/sysroot" \
  --glibc-profile "$SDK/profile.json" --receipt dash.json
xorriso -osirrox on -indev "$ISO" -extract /DASH.ELF installer.bundle
python3 -B scripts/xos_bundle.py verify installer.bundle --json > bundle.json
```

取 `bundle.json` 内 Dash 的 `data_off` 和 `data_len`，与 `dash.json` 中 `elf`
指向的文件逐字节比较。复跑安装时将冻结的 `xos-install-dash.iso`、安装清单、
系统清单和同一 build ID 的 `user_hello.image.elf` 只读置于验收树的 `build/`，
运行 `python3 -B tests/iso_dash_install.py --external --report "$REPORT"`。
本次复用只读 SDK 与介质，验收后保留约 20 MiB 的本地输入和输出。

本次通过 Dash 对应源码重建和安装路径，后续仍需复验 CPython/zlib 独立重编，
并按最终发行资产核对各静态程序的运行库替换及分发材料。
[证据索引](../reports/glibc_v2_dash_receiver_20261127/manifest.json)
