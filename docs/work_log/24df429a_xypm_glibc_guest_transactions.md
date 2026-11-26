# 24df429a · glibc xypm 客体事务

2026-11-26 · `build_xypm.py` 接受显式 glibc C/C++ 候选。它保留 xypm 和
恢复器入口，并把实际原生 files 客户端及依赖一起交叉构建。glibc 候选的维护租约走
现有 `file::client`，与 libc 文件访问共用代理的请求序号、时限及失效状态。
冻结 SDK 的维护入口继续使用旧请求序号钩子。包格式和客体数据库沿用 v1。

```sh
python3 scripts/create_xypm_profile.py create --runtime-family glibc --cxx \
  --sdk-build "$XOS_GLIBC_SDK_BUILD" --id xos-x86_64-glibc-xypm-v1 \
  --output build/glibc-xypm/profile.json
python3 scripts/build_xypm.py --sdk "$XOS_GLIBC_SDK_BUILD" \
  --profile build/glibc-xypm/profile.json > build/glibc-xypm/xypm.json
python3 tests/package_p2_transactions.py --system "$XOS_SYSTEM_BUILD" \
  --xypm-build build/glibc-xypm/xypm.json --profile build/glibc-xypm/profile.json \
  --output build/glibc-xypm/guest
```

Linux arm64 通过匹配的 GCC 16.2.0 和 binutils 2.47 生成真实 xypm ELF 和 XPK。
用 `db8e15dd` 构建的正常 XOS 镜像及 QEMU 11.1.2 通过 8 组。未取得维护
租约时拒绝写入，错误的包摘要保留状态并可恢复，安装、升级、移除跨实际重启生效。
空受管目录被清理。用户写入的文件和无关用户数据均保留，来宾和离线视图一致。
每条客体命令恢复资源 `129795 / 2 / 0`。逐步故障注入、断电、扇区撕裂与通过
glibc xypm 进行自升级仍待单独验证。

| 工件 | SHA-256 |
| --- | --- |
| 系统 `1216ff833a45226f` manifest | `17492b3c290b182f79493d745bd3181ef432f03969b2e112fa7233bbf82bda98` |
| 系统 ISO | `5a011f534499dc0b9cbb7f9b41671706047ba4071c133aa82bf54af155c9357d` |
| glibc C/C++ SDK manifest | `a4a6b3c278e34773088b11bb2a352d96487b9234755b9fcb9c7fe96ab9ace96e` |
| 候选 profile | `86184f89b1173c84d1a6176e3cc5a2e0f20cead3152a179ffeec680b1e89d879` |
| `build_xypm.py` | `79039a23523a9c1204190cfcb8ac73e630a0907a7171d9f28da868231fd0dee1` |
| `xypm.cpp` | `852ef8127417ebff3ce123ff666cd2296d9a21524b0045dbd3972d8bb11df3a0` |
| xypm ELF | `84a3a70ba9e3f3cfb108e49590269a1baa99cc9c940ec2417d8feb0f08e37134` |
| xypm XPK | `811be6632cabbad533a6016e4075c71ff49abaa4c301fc970d62eb67ca229047` |
| QEMU 事务回执 | `28c04ea5543203093ab0d2c844dc48f3708e0fdbce62516cd6298a2cdcd1b87b` |

## newlib 回退演练

在同一系统上使用先前通过 C3 资格的 `xos-x86_64-pr144-c3-candidate` newlib
包管理器与独立工作盘复跑上述 8 组，全部通过。旧 ELF SHA-256 为
`3def19bd47a56d4eee0d4a14d761fcb2b44593cbe2cd940db82eac710877e3e4`，
旧 XPK 为 `4de07bf9eaa09bf48b74bac85ac69bd2e1ec4d69ee6ba1596825e27757673fd0`，
回退测试回执为 `74b1ab5a32db9ed158f46c3d866bae45eba1ddd0ccae3a165d1619efdc5f982c`。
本次演练复用此前构建并验收的候选工具。在更早的 0.0.1-1024 SDK 上尝试从当前源码重建时，
编译器报告该 SDK 的旧原生 files 客户端名称和当前 xypm 源码不同。
