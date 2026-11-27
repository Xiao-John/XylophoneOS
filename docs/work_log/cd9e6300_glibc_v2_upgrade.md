# cd9e6300 · glibc v2 候选升级与中断恢复

使用显式 v2 发行候选的普通 ISO `ce681c073de3d6c4`、实际安装 ISO、GNU Seed
发行工作盘和统一 SDK v2。系统和发行资产沿用 `8e66789c` 的冻结候选，回归
从 `be277e1d` 上的 `cd9e6300` 运行。Linux arm64 容器断网，QEMU 11.1.3
执行原生 x86-64 ELF。发行盘、两种 ISO、SDK、profile 和回执摘要均已核对。

## 客体结果

- 同一 v2 profile 下，编译旧 P2 源码及已有两个兼容接线。客体从空盘安装
  P2 和锁定的两个依赖包。分别正常自升级、在旧 `/usr/bin/xypm` 删除后的
  同步检查点 146 退出、冷启动内置恢复器并重试。恢复后的二进制、数据库、
  索引、依赖锁和用户文件与旧盘一致。重试冷启与正常升级记录一致，P3
  验证两个包的仓库闭包。
- 从只读挂载的发行初盘复制试验盘，使用安装 ISO 装入随附 Dash 与 xypm，运行
  CPython、gzip 和 IDNA。以发行 IDNA XPK 为基础生成测试修订 1，新增一个
  验收标记文件。客体在标记已写入、提交记录仍未发布的同步检查点 123
  退出。恢复器回滚包记录、索引和用户文件，核对所有发行包受管文件，原盘
  SHA-256 保持一致。由发行 xypm 重试后冷启执行同一 Python 检查，包清单
  包含新文件，资源回到 `129806 / 2 / 0`。
- 用已登记的历史 newlib P2 重建镜像和旧包建立工作盘。v2 端拒绝跨 profile
  升级，内置恢复器报告没有事务。拒绝盘与仅启动对照盘的全盘摘要一致，
  旧客体冷启后仍可读取旧包、应用和用户文件。旧镜像是先前绑定的历史源码
  重建产物，原发行二进制介质的范围见历史回执。

宿主 SDK profile 45 项和仓库 50 项通过。首次容器启动缺少历史 Git 对象挂载，
修正为只读挂载后从真实历史输入重建。同步退出用于事务重放，物理断电和扇区
撕裂仍待验收。本文的升级对象是同 profile 下的包，跨 profile 继续使用独立工作盘。
[冻结摘要](../reports/glibc_v2_upgrade_20261127/manifest.json) ·
[历史 P2 输入](3ce98ac7_glibc_g4_xypm_p2_p3.md)

## 重跑

使用冻结发行 kit，令 `SDK` 指向 `application-sdk/sdk`，`PROFILE` 指向同 kit
的 `profile.json`。旧 P2 构建使用 Git 历史对象，容器里需可读。

```sh
python3 -B scripts/build_xypm.py --sdk "$SDK" --profile "$PROFILE" > "$NORMAL"
python3 -B scripts/build_xypm.py --sdk "$SDK" --profile "$PROFILE" --fault-injection > "$FAULT"
python3 -B tests/build_xypm_p2_glibc_fixture.py --sdk "$SDK" --profile "$PROFILE" --output "$OLD_P2"
python3 -B tests/package_g4_cross_version_guest.py --old "$OLD_P2/manifest.json" \
  --new "$NORMAL" --fault "$FAULT" --profile "$PROFILE" --next-profile "$PROFILE" \
  --old-image "$SYSTEM/xos-install.iso" --new-image "$SYSTEM/xos-install.iso" --output "$CROSS_VERSION"
python3 -B tests/glibc_release_upgrade_guest.py --release "$RELEASE" \
  --fault-build "$FAULT" --output "$COMPOSED_UPGRADE"
```

拒绝与回退用例将旧包回执、旧 profile 和旧镜像传入同一个
`package_g4_cross_version_guest.py`，保留 v2 的新包、profile 和普通 ISO。
