# 831b1c57 — glibc files-extra 宿主验收来源前后绑定评审修复

日期：2026-11-25。基线 `e8a79aa`，对应 PR #160 review comment
`4694694632` / thread `PRRT_kwDOVU8IlM674tK1`。本组仅修改宿主验收脚本与
定向负向探针，不改变 libc、files 服务、ABI 或 SDK 内容。

## 复现与修复

旧 `glibc_files_extra_host.py` 在编译、运行完成后才计算源码摘要。新增独立
`glibc_host_source_binding.py` 在私有输入副本中调用真实 gcc/g++，最终链接
成功后由编译器 wrapper 给 `xos_file_positioned.c` 追加一条有效注释。已链接
程序继续执行旧字节，旧 runner 却返回 0、标记 passed，并记录修改后的摘要。
源码编辑发生在确定的链接完成边界，测试不依赖延迟或调度运气。

修复后，在第一条编译命令前冻结全部 translation unit、仓库头文件、实际
files 服务及被包含的 fixture、磁盘生成脚本和 runner。通过前重新收集同一
输入集合并逐项比较，加入、删除或更改输入均会失败。报告的 `sources` 始终
保留编译前摘要，变化后的副本放在 `sources_after`，仅一致时设置
`source_snapshot_verified=true` 与 passed。

同一真实链接后变更注入现在返回 1，报告 failed，明确说明
`source inputs changed during qualification`，并保留原始摘要。负向探针
只修改自己的临时输入副本，原工作区与并行构建保持独立。

## 实际验收

| 检查 | 实际结果 |
|---|---|
| 旧 runner 的链接后变更 | 复现 false pass，报告关联到新摘要 |
| 修后同一变更 | 明确失败，保留编译前摘要 |
| files/FatFs/glibc 真实宿主集成 | 8 / 8 组通过，输入前后完全一致 |
| 同组 ASan/UBSan | 8 / 8 组通过，输入前后完全一致 |
| 公开目录/定位 I/O 客体 | 3 次通过 |
| native parent 与 glibc child 共享描述客体 | 3 次通过 |
| 每次客体的资源恢复 | 129715 free pages、3 tasks、1 completion |

新系统 build ID 为 `71a6f76cd0a9ebc5`，kernel 829592 字节。SDK 复用此前完整
构建的 `glibc_files_extra_sdk_qualified`，其输入集合与当前代码逐项相同，客体
入口再次验证成套产物。一次误选另一诊断候选目录 `glibc_files_extra_sdk_final`
被正式入口以 `SDK input snapshot changed` 拒绝，QEMU 尚未启动；该失败记录
与更正后的 6 次真实通过一起保存。

宿主使用 GCC/G++ 14.2.0；系统使用 preview release 的 GCC/G++ 16.2.0、
binutils 2.47.20260726、NASM 3.02。QEMU 实际为 11.1.3，仓库锁为 11.1.2。
serial-only，QMP 关闭，私有 FAT32 介质。LSan 因 ptrace 环境未运行；本组未
重复既有 legacy guest、物理机器和 QEMU 11.1.2。

## 复现命令与证据

`XOS_PREVIEW_RUN` 指向 preview 工具环境，`XOS_PR160_PRE_REVIEW` 指向本修复
前的 PR #160 版本。输出目录应为空。

```sh
python3 tests/glibc_host_source_binding.py --profile files_extra \
  --baseline "${XOS_PR160_PRE_REVIEW}" --expect passed --output build/files_source_binding_before
python3 tests/glibc_host_source_binding.py --profile files_extra \
  --output build/files_source_binding_after
python3 tests/glibc_files_extra_host.py --output build/files_host_review
python3 tests/glibc_files_extra_host.py --sanitize --output build/files_host_review_sanitized
"${XOS_PREVIEW_RUN}" python3 scripts/build.py --output-dir build/files_system_review
"${XOS_PREVIEW_RUN}" python3 tests/glibc_static_guest.py \
  --system-build build/files_system_review --glibc-build build/glibc_files_extra_sdk_qualified \
  --suite files-extra --output build/files_guest_review_qualified --repetitions 3
python3 scripts/verify_evidence_index.py docs/reports/glibc_files_source_review_20261125/manifest.json
python3 tests/check_public_evidence_paths.py --commit HEAD --base e8a79aa \
  --output build/files_source_review_public.json
```

冻结证据在 [glibc_files_source_review_20261125](../reports/glibc_files_source_review_20261125/manifest.json)。
根清单覆盖每个导出，`qualification.json` 保存原始散列与路径模板化关系。
导出日志规范化宿主位置、CRLF 和行尾空白，旧失败与新结果分别保留。

组合 agent 接入这两个 test 文件即可；若合并新增 terminal 对象导致 host
链接输入增加，应同步扩充 `source_snapshot()` 的 compiled source 集合。
root 负责更新原 PR 和全局 state。本修复没有修改共享 file API runner，
该 runner 的同类来源加固由 root 单独处理。
