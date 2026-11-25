# 整合基线许可材料修复

2026-11-25，基线 `85127256aa3286d44de5c7f739271c60f4e491a7`。组合验收的
`scripts/license_audit.py` 先后拒绝了 ncurses 来源锁及 XOS SQLite VFS 的旧
登记摘要，然后拒绝了近期端口中缺失标识的 XOS 自研文件。处理范围为现有登记及其
自研文件头部。

- #141 把 ncurses 6.5 来源锁改为统一端口结构。对锁定发布归档重新核验 SHA-256，
  比对 COPYING 原文和 terminfo 源文件的许可前缀。归档和两份声明保持原样，登记
  新来源锁文件的摘要 `d4d2d05b79bf7848e1131d462d3d0c55e4d88f8769ec63f934f0b41c5ba7be96`。
- `e3f2fe3d` 为 XOS SQLite VFS 加入设备/文件身份检查和路径规范化。复核该增量及
  已有 Apache-2.0 标识，登记适配器的明确许可和当前摘要
  `87e7788346192b17914ff98a3240444dfed5d0a5512e968b284f5d826765b844`。
  SQLite 上游来源锁和许可原文继续沿用。
- 依据 #117、#120、#132、#136、#141 的新增历史，为 18 份 XOS 端口构建配方、
  判定器、样例、测试和兼容代码补齐 Apache-2.0 标识。上游归档、补丁和冻结证据保持
  原文件内容。

```sh
XOS_LWIP_SOURCE_ARCHIVE=<locked-archive> python3 scripts/build.py --output-dir build/campaign-license-repair-v3
python3 scripts/license_audit.py --build build/campaign-license-repair-v3
python3 scripts/ports.py check --all --json
python3 tests/bc_build_validation.py
python3 tests/ncurses_build_validation.py
python3 tests/ports_build_failures.py
```

实际构建 `fb5deb06e84406a9`，GCC/G++ 16.2.0、Binutils 2.47.20260726、NASM 3.02。
许可检查 10 份 SDK 材料及 933 份源文件通过，现行登记为 0 open，
`byte_level_member_provenance` 仍为 deferred。全部 11 个端口元数据和 4 项相关
宿主测试通过。报告 SHA-256
`9bbee69afd693fcfb87ea6cae8e1974e480d7d707d51d06c4dfd819a275a54c5`，
ISO SHA-256 `00535f53730dddc51494785ef60d2a264f79412e5a403845d6fce6a880164070`。

已验证登记材料与重建 SDK 一致。逐成员或第三方分发法律审查及新发行验证不在这份
报告范围内。下一次主线组合须重建后再次执行材料检查。
