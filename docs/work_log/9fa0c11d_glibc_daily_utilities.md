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
