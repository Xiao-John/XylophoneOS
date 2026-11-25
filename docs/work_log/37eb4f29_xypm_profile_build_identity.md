# xypm 候选 SDK 构建身份准入复查

2026-11-25。对应 PR164 评审 4694723200，基于本地 `d372657c`，
远端等价提交 `7e77d17d86c8ce0d034c275b0db42a75d35a13ab`。

newlib 候选过去可以接受缺少 `build_id` 的 manifest，而正常应用构建入口会
读取这个字段。现在准入要求生成器使用的 16 位小写十六进制身份，缺失、错误
类型、空值、错误长度及非法字符均在生成候选前拒绝。原有效 SDK 继续通过。

合成 fixture 补上有效身份，新增缺失和畸形身份两组检查。测试 runner 同时在
执行前保存四个实现输入的摘要，并在输出 `passed` 前复查；报告保留实际初始
输入，变化时返回失败。此次未修改既有候选、冻结 SDK、系统或安装数据库。

## 实际结果与复现

```sh
python3 tests/xypm_sdk_profile_host.py --output build/xypm_profile_build_id_final
python3 scripts/create_xypm_profile.py verify --runtime-family newlib \
  --sdk "$XOS_NEWLIB_SDK" --profile "$XOS_NEWLIB_CANDIDATE"
python3 scripts/verify_evidence_index.py docs/reports/xypm_profile_build_identity_20261125/manifest.json
```

41/41 合成宿主检查通过，前后输入相同。实际 P3 preview candidate 重新核验
通过，其 SDK 整树 SHA-256 为
`092349e37c424fd3b800bd4bd8718ed0e01af80dc0b2563ee9c8a5e4735e9f24`。
`verified_system_builds` 仍为空，来源/客体资格按原模块记录；本增量没有运行
新的系统客体，也没有为 SDK 重新签发来源资格。

公开记录：[证据清单](../reports/xypm_profile_build_identity_20261125/manifest.json)。
