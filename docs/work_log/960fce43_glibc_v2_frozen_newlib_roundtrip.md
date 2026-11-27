# 960fce43 · v2 与冻结 newlib 的隔离回退复验

将当前 v2 普通系统 `1f593b6ca9cd7904` 与其 2,049 项源及实物绑定。
v2 SDK、C/C++ 包和工作盘沿用[已验工作区选择](4c8a56a1_glibc_v2_workspace_default.md)。
冻结侧使用原 0.0.1-1024 启动软盘 `2c3876e640840ff5`、原 SDK、原发行工作盘及
历史回退验收中已含旧应用和旧用户文件的盘。SDK、媒体、三份原始盘和旧包的
实际字节都按既有回执核对。本次复用原生 ELF 和两个已验证的宿主 FAT 工具。

## 宿主检查

两个方向均拒绝错 profile 的包与已登记数据库。原发行无 profile 的工作盘副本
拒绝 `list`、`install` 和 `repo-install`，盘摘要保持且没有候选盘输出。
临时移走私有 v2 kit 后状态查询失败，显式切到冻结 SDK 成功。恢复 v2 后
注册文件字节与初始一致。输入预检和实际复跑各通过 11 项，共用同一套只读原件。

首次预检的 420 MiB 内存盘遇到 `ENOSPC`。原发行盘的宿主写入入口先暂存稀疏
事务副本，再检查 profile。扩大到 480 MiB 后触发并核对预期 profile 拒绝。
读取只读原件时使用支持只读打开的 xypm FAT 后端，客体使用已有工具操作临时盘。

## 三次冷启动

| 次序 | 介质和实测 | 退出前后资源 |
| --- | --- | --- |
| v2 | 当前普通 ISO。原有 C 程序读盘并核对 glibc 2.44，C++ 运行容器、线程和异常。 | 129709 / 3 / 1 |
| 冻结 newlib | 原版软盘和历史用户盘副本。运行原 ELF，读取旧文件并同步追加 `selection`。 | 130342 / 2 / 0 |
| 返回 v2 | 同一当前普通 ISO 和同一 v2 盘再次运行 C/C++，已登记文件和用户数据读回。 | 129709 / 3 / 1 |

三个 QEMU 11.1.3 客体均在断网 Linux 启动，分别有 5,632,660、4,914,620
和 3,821,516 KiB 可用内存。前一组合容器移除后才启动，三次均满足 3.5 GiB
门槛。测试盘为有界内存盘中的稀疏副本。三个原始盘在结束后再次核对完整摘要，
与开始前一致。工作盘用途和 SDK profile 始终对应各自系统。
[回执、启动条件与三份原始串口](../reports/glibc_v2_current_frozen_roundtrip_20261127/manifest.json)

## 复跑

本次使用的 `replay.py` 与验收回执中的 `runner_sha256` 一致。
`entry.sh` 安装已验宿主 FAT 工具到临时缓存并拒绝隐式编译，之后启动运行器。
[精确运行器](../reports/glibc_v2_current_frozen_roundtrip_20261127/replay.py) ·
[容器入口](../reports/glibc_v2_current_frozen_roundtrip_20261127/entry.sh)

在宿主设置以下路径，使用 [输入回执](../reports/glibc_v2_current_frozen_roundtrip_20261127/inputs.json)
核对现有实物。

| 变量 | 绑定输入 |
| --- | --- |
| `SOURCE_CHECKOUT`、`CANDIDATE` | 精确 `960fce43` 源码树，以及该次构建的 `candidate_manifest.json` 和 `system/` 所在目录。 |
| `V2_FIXTURE` | 前次验收目录中的 `c.xpk`、`cpp.xpk`、`glibc-work.img`，另含 `repository/` 和 `lock.json`。三份现成素材的宿主路径分别是 `$V2_FIXTURE/c.xpk`、`$V2_FIXTURE/cpp.xpk`、`$V2_FIXTURE/glibc-work.img`。若分开存放，分别将它们只读挂到相同容器目标，并在 `/v2-fixture` 提供仓库与锁。 |
| `V2_KIT` | 上述包和盘对应的 v2 安装 kit，含 `profile.json` 和 `sdk/`。 |
| `FROZEN`、`HISTORICAL`、`FROZEN_SDK_ARCHIVE` | 含 `release-images.tar.gz`、`frozen.xpk`、已解出的 `xylophoneos_revival_0.0.1-1024_images/` 的目录。历史验收目录提供 `guest-05/report.json`、`guest-05/old-work.img` 和原版已解出的 SDK。单独指定原版 SDK tarball。 |
| `FAT_HOST_CACHE`、`XYPM_HOST_CACHE` | Linux arm64 上已有且源码摘要相同的两个 FAT 缓存，分别为 `build/host_tools/linux-aarch64` 和 `xos_xypm_host_0`。 |
| `RECEIVER_IMAGE`、`OUTPUT` | 已有 Linux arm64 容器镜像和本次独立输出目录。本次镜像摘要与 QEMU 版本见资格回执。 |

将本条报告所在仓库的 `docs/reports/glibc_v2_current_frozen_roundtrip_20261127`
设为 `REPLAY_FILES`。确认其他组合客体已结束，以及 Linux 可用内存达到 3.5 GiB。
以下命令沿用本次实际挂载角色与内存盘容量。

```sh
mkdir -p "$OUTPUT" "$SOURCE_CHECKOUT/build"
cp "$REPLAY_FILES/replay.py" "$REPLAY_FILES/entry.sh" "$OUTPUT/"
docker run --rm --network none --cpus=2 --memory=2200m --memory-swap=2200m \
  --tmpfs /scratch:rw,exec,size=480m --tmpfs /workspace/build:rw,exec,size=16m \
  --mount "type=bind,source=$SOURCE_CHECKOUT,target=/workspace,readonly" \
  --mount "type=bind,source=$OUTPUT,target=/out" \
  --mount "type=bind,source=$CANDIDATE,target=/candidate,readonly" \
  --mount "type=bind,source=$V2_FIXTURE,target=/v2-fixture,readonly" \
  --mount "type=bind,source=$V2_KIT,target=/kit,readonly" \
  --mount "type=bind,source=$FAT_HOST_CACHE,target=/fat-cached,readonly" \
  --mount "type=bind,source=$XYPM_HOST_CACHE,target=/cached,readonly" \
  --mount "type=bind,source=$FROZEN,target=/frozen,readonly" \
  --mount "type=bind,source=$HISTORICAL,target=/historical,readonly" \
  --mount "type=bind,source=$FROZEN_SDK_ARCHIVE,target=/frozen-sdk.tar.gz,readonly" \
  "$RECEIVER_IMAGE" sh /out/entry.sh
```

在 `entry.sh` 后追加 `--inputs-only` 可只做输入与宿主检查，回执写入
`inputs.json`。完整复跑写入 `report.json` 和三份压缩串口。
