# 9fa0c11d · 日用工具的 glibc 迁移

2026-11-26 · 隔离构建显式绑定 glibc C SDK 的应用 profile，要求
`directories` 能力，通过独立 [路径变更候选](69af117e_glibc_path_mutations.md)
提供的实构建 sysroot。sbase 上游 commit `c546c3a5724c81cee9a11d816a38ccdf17472129`
与源码文件摘要均与现有源锁一致。全部 13 个工具使用目标 GCC 16.2.0
和 binutils 2.47 构建。旧 newlib 构建入口仍可按原调用方式使用。

```sh
python3 scripts/build_daily_utilities.py --sdk "$XOS_GLIBC_SDK_BUILD" \
  --glibc-profile "$XOS_GLIBC_PROFILE" --source "$SBASE_SOURCE" --output-dir build/daily-glibc
python3 tests/daily_utilities_smoke.py --foreground --image "$XOS_SYSTEM_ISO" \
  --dash "$XOS_DASH_ELF" --tools build/daily-glibc --report build/daily-glibc-foreground.json
```

QEMU 11.1.2 以前台模式通过 12 个工具，覆盖普通文件操作、目录状态、重命名后
读回、文本输出和关机后独立回读字节。dash 整段运行和 xsh 单独执行 `ls` 后均恢复
`129698 / 3 / 1`。系统为路径变更的普通镜像 `7a6b2533dead9800`，dash ELF
来自冻结的 C3 兼容入口。完整 DU12 脚本在第一个外部重定向的 `cat` 返回 126。
`tee` 和完整管道、外部重定向及 XPK 安装后回退留待最新 descriptor transfer
组合验收。构建清单独立记录 13 个 ELF，当前客体资格为 `passed_subset`。

| 工件 | SHA-256 |
| --- | --- |
| 系统 ISO | `9af1dee98b01b681ec7f0d3e7e80aa51ad33b2ddcaf630274fbd3c1ae88729b5` |
| glibc SDK manifest | `74cb7ddcc19240d7782dfd20a82924318d1046956f4950e5da18e81a2c8dc79b` |
| 应用 profile | `e2aae837fdd7b6cf342f3f65af57c6d9ae292eda59e47b8ebf8d1d246237e838` |
| 工具构建清单 | `cdfd44a5d008244a6a6bb60d77aafff54663d7d4963f064bbc43caebc8aa6f96` |
| 前台验收回执 | `e9cd69f58de6c9e1ce9e711fbd067c3ce2ceae36df630c1aaee6684aa6a068e3` |

## 完整 DU12 组合验收

本次从日用工具及路径变更提交组合已验证的 glibc dash 重定向。初次使用
签名验证 SDK 和 glibc dash 运行原脚本，在第 6 行的 `cat` 得到 126。
13 个 glibc 工具现在链接实际的启动描述符接收实现，并在 ELF 声明现有
`.xos.exec`。构建清单绑定接收声明的源码摘要。

预览 dash 可在管线首段运行内建 `printf`。该段支持正常的引号和参数，
并限制赋值、重定向及可改变 Shell 状态的替换。后续外部进程启动后，Shell
通过同一个原生管道写入，关闭写端并收集各段状态。其余内建、函数及复合
管线仍沿预览范围检查。

完整验收使用原有 runner 和同一份 `du12.sh`。默认设备上的 180 秒等待
未收到返回提示。复验启用正常的 xsh 进程 trace 并把同一提示的等待预算
设为 420 秒。命令输入、退出判断和宿主回读断言沿用原脚本。

```sh
python3 tests/daily_utilities_smoke.py --image "$XOS_SYSTEM_ISO" \
  --dash "$XOS_GLIBC_DASH_ELF" --tools build/daily-glibc \
  --report build/daily-glibc-full.json --dash-timeout 420
```

| 工件 | SHA-256 |
| --- | --- |
| 普通系统 `801fb217573a9a5f` 的 ISO | `72f4f2771aaa4b58fc83fa5dc4ba6a6c95f1a8eb5828c66c83c0e2045fcd2db6` |
| 签名验证的 glibc 2.44 C SDK manifest | `2878955bbd6f589d9a2227c53dc4c1ff35157edb38ccaac7347421f058e082a4` |
| 同一 C SDK 压缩包 | `d8004f71946112550c3cd96757dddc537418a1c189d6861dc29597e368a86bc2` |
| 目录能力 profile | `a8aa19b1f2a96bc4c3f85b3aca53f9de3bb787eeca884e493ab834ed1a1deb1a` |
| 13 个目标 ELF 的工具清单 | `0a3436dc4b9baf3215c2afe388b697a824c3cb135d590dbd755b17bd1c20c305` |
| 显式选用的 glibc dash ELF | `b6957d9114bf298a511235d7717aaef43aa92a5325c4a01a9e1660f97fa76ec6` |
| 原 DU12 runner | `b5a15531d5d23dd2be0f28cacb4aa744e78cc29b96c1ab6f59a1a2c668e5bbff` |
| 原 `du12.sh` | `56ed889fd876e024892f0fb16df86f057f99a031181f978efca21f564e785f28` |
| 完整 DU12 回执 | `96f7e2dcd06bf3540098c98941d7c3f538848f3756c3498ceee6d971c9b08be0` |
| 完整 DU12 串口 | `56f83dc0a637cbc0eb11b2864ba971ad463f563b9b4a62394d38d146e7256dd9` |
| 同版路径变更回执 | `a5b9f79c24b96ac615fe106423445ae0fb316b5ade62ba7d4ddee381ac634c16` |

QEMU 中的完整 DU12 回执为 `passed`。原脚本覆盖全部 13 个工具，59 次外部
启动完成后打印 `DU12_OK` 并退出 0。xsh 单独执行 `ls` 退出 0，文件同步后
独立读回的 33 份文件逐字节匹配。路径变更单独门禁两轮通过。

正式 CLI 复验使用 `--dash-timeout 420`，shell 脚本摘要保持一致。原有
180 秒为默认值，非正数被参数检验拒绝。复验重建系统 `d520edbdbaf0a035`
并重新核对同一 SDK、13 个 ELF 与 dash 的输入。

| 复验工件 | SHA-256 |
| --- | --- |
| CLI 复验 ISO | `ddabede6ed0f7575ebf40204f125f9807910fceff35deab104beba07443caa12` |
| CLI 完整验收 `passed` | `620fe87235cfca10118fcaef0dab56ec9efa35d657469b98498affa5c4982df4` |
| CLI 复验同镜像路径操作 2/2 | `1f5826ed2501812e357a77787508740c159396b3fe6e719d663dc8a015c6f22b` |
| 双入口 dash 回归 42/42 | `10452033ee70bbf66acbd4c5695c6d43c67fed428f235eac039b2b7eb0aa1f20` |
| 13 个 glibc 工具的压缩包 | `20d0b082af7a5ca9255ad0531f6a77ce7b35837f2d4131a2b3c8c7d16ab2efdf` |

双入口测试使用两个不同的启动路径验证 10,037 字节的内建 `printf` 管线。
42 项测试均恢复资源基线 `[129698, 3, 1]`。默认 newlib dash ELF 仍为
`94be9cc12698f6da03be0737e938f0c3d1f42061c3f89f3bcec869fcfc191067`。

显式安装镜像也通过现有 A3/A4 验收。3,376,744 字节的 glibc dash 可从 ISO
安装到新 FAT 磁盘，xsh 可找到 `/usr/bin/dash`，`dash -i` 的普通输入、
输出与退出均完成。该目标的镜像载荷额度为 32 MiB。验收回执为
`2e8225cc0c55a9e705a9c85069cc5bb5d62b0bd6a61af38d66742f531c7f0f67`。

## 默认切换仍需完成的工作

- 正常系统 SDK 仍从 newlib 装配。自动 dash 安装从既有 newlib 缓存选工件。
  默认切换需要成套绑定 SDK、发布 profile、安装镜像和可复验的回退工件。
  [系统 SDK 装配](../../scripts/user_build.py) · [dash 安装选择](../../scripts/install_dash.py)
- 日用工具的 XPK 构建仍读取 newlib SDK 的许可证布局。对本 glibc sysroot
  实测先在 `LICENSE` 路径返回缺失。XPK 同时要求 `stdio_transfer`，
  当前 glibc 候选 profile 拒绝该 feature。发布路径仍需运行安装、使用与回退验收。
  [日用工具打包](../../scripts/package_daily_utilities.py) · [SDK profile](../../scripts/xypm_sdk_profile.py)
- 当前 glibc shell 范围保留预览限制。正常 `fork`、`exec` 替换、命令替换、
  复合管线，以及通用 spawn 文件动作和出站终端继承仍有明确失败入口。
  [glibc fork](../../src/ports/glibc/sysdeps/xos/fork.c) · [spawn 文件动作](../../src/ports/glibc/sysdeps/xos/spawni.c) · [终端契约](../contracts/glibc_terminal_v1.md)
