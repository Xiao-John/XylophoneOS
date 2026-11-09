# 0216 Season-3 报告修复：大小写 rename、写失败回滚、bundle 名称区、脚本边界

输入为 CONTEST 三份 `found_bug_s3.md`（contest-1/2/4）。去重后共 **11 个独立问题**，
全部在基线 `fdadfe77`（= 证据 build `4bd9c9e9b18f68bc`）的当前源码中逐一确认存在，
**无已修复项可跳过**。分支 `codex/bug_hunting_s3_fixes`，按文件互斥并行修复。

## 去重映射（报告 → 修复）

| # | 问题 | 来源（重复合并） |
|---|---|---|
| A | 大小写 rename 被 `names_equal` 折叠短路，`f_rename` 永不执行 | contest-1 S3-01 + contest-2 S3-BUG-01 |
| B | `make_iso.py` 缺长度上界，超长名未捕获 `ValueError` traceback | contest-1 S4-02 + contest-2 S3-BUG-02 |
| C | bundle 名称区紧凑性只在宿主校验，客体安装器接受重叠/留空 | contest-1 S3-02 |
| D | `work_disk.transfer` 只按 `/` 拆路径，`\` 绕过点/保留名校验 | contest-1 S4-03 |
| E | 写越界零填充成功后 seek/`f_write` 失败不回滚 | contest-1 S3-04 |
| F | 零长度写在偏移超 EOF 时仍扩展文件（POSIX 违规） | contest-1 S3-05 |
| G | `work_disk` 缓存 stamp 非 UTF-8 时 `UnicodeDecodeError` 逃逸 | contest-2 S3-BUG-03 |
| H | rename 已提交后 `f_stat`/identity 失败报 `status::io`，客户端误判 | contest-4 S3-1 |
| I | `replace_commit` 已提交后 identity 失败置 `recovery_failed` 全局故障 | contest-4 S3-2 |
| J | 磁盘满 0 字节写回 `ok`，客户端落 `EIO` 而非 `ENOSPC` | contest-4 S3-3 |
| K | rename 备份存在性判断用 `!= FR_NO_FILE`，`FR_NO_PATH` 误判 busy | contest-4 S3-4 |

## 代码修复

- `src/user/services/files.cpp`（A/E/F/H/I/J/K）：
  - A：新增 `names_equal_exact()` 逐字节比较；`same` 分支仅在字节不同时调 `f_rename`，
    成功后 best-effort `f_stat` 前后快照 + `identity_for_key`/`move_identity` 迁移身份
    （避免旧 `file_identities[]` 项泄露；失败只留 stale 内存项，不影响回复）。
  - E：`op::write` 抽出 `undo_failed_write()` lambda（仅当 `f_size > size` 时
    seek(size)+`f_truncate`，再尽力恢复写前偏移且**绝不超过恢复后长度**——`f_lseek`
    超 EOF 会用未清零簇重新扩展），三个失败路径（grow 失败、seek 失败、总写失败）
    统一回滚；grow 失败路径行为与原实现等价。
  - F：`in.length == 0` 在最前直接回 `ok`，不移偏移、不扩展、append 亦无副作用。
  - J：`written == 0`（`in.length > 0` 已保证）时 `FR_OK` → `status::no_space`
    （客户端 `error_from_file` 已映射 ENOSPC），错误码则 `from_fr`；部分写（`written>0`）
    保留 POSIX 语义照旧 `ok`。newlib `result==0 → EIO` 分支在服务端修复后不可达，未改客户端。
  - H：rename 已提交后 `f_stat`/`move_identity` 失败仅跳过内存簿记，恒回 `ok`
    （identity 表纯内存、重启清空，报告确认无持久影响）。
  - I：`replace_commit` 中 identity 更新降级为 best-effort；**无论 stat 成败都执行
    `finish_recovery`**（否则残留 backup 会把后续 rename 顶成 busy 直到重启）；
    仅 `finish_recovery` 失败才置 `recovery_failed` 回 `io`（journal 残留由启动恢复接手）。
  - K：改为 `!missing(f_stat(backup_name, ...))`，`FR_NO_PATH` 不再误判 busy 并丢 journal。
- `src/user/services/file_ui.cpp`（C）：预检阶段（任何落盘之前）收集各成员
  `(name_off, name_len)`，按 `name_off` 排序后要求首项从 0 起逐项无缝、总和 ==
  `names_bytes`，否则整容器拒绝（`[files] bundle names not compact`/`unused`），
  与宿主 `scripts/xos_bundle.py` 接受集对齐；只补紧凑性一条，宿主已有条件客体原本就有。
- `scripts/make_iso.py`（B）：`--file` 名 >220 字符拒绝（33+len+2(`;1`) ≤ 255 单字节上限）；
  `record()` 加 `SystemExit` 防御，杜绝未捕获 `ValueError` traceback。
- `scripts/work_disk.py`（D/G）：`transfer()` 拒绝含 `\` 的路径（FatFs `IsSeparator`
  认 `\` 为分隔符，FAT 文件名本身不允许，拒绝不误伤）；`_cache_valid` 捕获扩为
  `(OSError, ValueError)`，坏 UTF-8 stamp 视为缓存无效走重建。
- 测试：
  - `tests/fixtures/file_semantics/file_semantics.cpp`：修正用例 12 假阴性
    （`f_stat` 会回填请求拼写 → 改用 `f_opendir`/`f_readdir` 断言存储目录项）；
    新增注入 `write_fail_nth`（第 N 次 `f_write` 回 0 字节 `FR_OK` 模拟满盘）；
    新增用例 16（零长度写不扩展）、用例 17（零填充成功后数据写 0 字节 →
    `no_space` 且回滚到原长）。三用例按构造在修复前必失败。
  - `tests/make_iso_names.py`：221 字符负例（干净拒绝、无 Traceback）+ 220 边界正例。
  - `tests/work_disk_cache.py`：坏 stamp 负例、含 `\` 路径负例（桩证明校验先于工具执行）、
    坏 stamp 下 `host_tool()` 正常重建（临时树 + 桩，不碰共享 `build/`）。
  - `tests/test_xos_bundle.py`：补尾部未用字节负例（重叠已有覆盖）。
  - `tests/bundle_installer_reject.py`：新增客体 `name-overlap` 用例
    （entry1 `name_off` 4→3，期望 `[files] bundle names not compact` 且 dash 未装）。

## 证据（2026-11-09，build `dd5537bfe75ee995`，kernel 512080 字节）

宿主（Apple clang 21.0.0 / Python 3.12.15）：

```text
python3 tests/file_semantics.py       FILE_SEMANTICS_CASES_PASSED=17
python3 tests/file_recovery_faults.py RECOVERY_CASES_PASSED=21
python3 tests/test_xos_bundle.py      Ran 27 tests OK (skipped=1，正控 idna 缺席时既定 skip)
python3 tests/make_iso_names.py       ISO_NAME_CASES_OK
python3 tests/work_disk_cache.py      WORK_DISK_CACHE_OK
```

客体（QEMU 11.1.2，x86_64-elf-g++ 16.2.0）：

```text
python3 tests/file_posix_guest.py          PASS: 11 file posix checks | build dd5537bfe75ee995
python3 tests/bundle_installer_reject.py   PASS: 6 cases（bad-name/reserved1/bad-magic/
                                            non-elf-legacy/later-digest/name-overlap）
python3 tests/iso_bundle_install.py        passed（正常安装正路径，防 C 误伤合法容器）
python3 tests/file_smoke.py                PASS: 8 E05 checks | build dd5537bfe75ee995
python3 scripts/build.py                   OK（全量构建两次：修复后 + 基线对照）
```

idna 测试夹具：`build/idna-3.20.xpk` 原缺失，按 `src/ports/cpython/idna_lock.json`
的 `wheel_url` 下载 wheel，SHA256 与 lock 完全一致（`ab7ae712…4582c`）后经
`scripts/xypm_python_wheel.py` 打包（`package_sha256 eb8e719a…`）。

## 失败 / 未运行 / 既有问题

- **`file_recovery_guest.py` corrupt 模式失败——既有问题，与本组修复无关（已实证）**：
  期望 `mkdir /blocked` → `error=-7`，实际被 supervisor 门禁拦截
  （`maintenance: persistent recovery required; command blocked`，supervisor.cpp:423，
  门禁由 d6363f83 引入）。failed-closed 下三个 xypm marker stat 返回 `io` → 门禁开启，
  而 `mkdir` 不在白名单，该期望与当前门禁设计矛盾。**用基线（HEAD 无本组改动）
  重建 `4bd9c9e9b18f68bc`（= 0215 证据 build）复跑，同断言、同输出同样失败**；
  0215 记录的 "file_recovery_guest passed" 应是在遗留 `build/audit_01/system` 旧镜像上
  取得（当前 `scripts/` 已无构建该路径的入口）。未修：改测试期望还是改门禁白名单
  属契约裁决，不在本组 11 项范围内。
- 未运行：`make smoke` 全套、真实满盘客体镜像注入（宿主用例 17 用注入模拟满盘）、
  E 的 seek-失败路径无独立注入用例（与 grow-失败共用同一 `undo_failed_write`，
  逻辑同源）、`xypm ensure` 客体故障注入。
- 未改客户端：newlib `write()` 的 `result==0 → EIO` 分支在服务端修复后不可达
  （`in.length>0` 时服务端不再回 `ok+0`），保留为防御性兜底。
- 已知限制：H/I 的"提交后 stat 失败"路径为 best-effort 内存簿记，未注入验证
  （需磁盘错误注入，静态核对）；A 的 identity 迁移在 `f_stat(new)` 失败时跳过
  （留 stale 内存项，无持久影响）。

## 下一位 agent 可直接执行的下一步

- 裁决并修复 `file_recovery_guest` corrupt 用例与 supervisor 门禁的矛盾
  （改测试期望为 blocked，或门禁放行 `mkdir`——需先定契约，见上）。
- 0215 遗留照旧：真实共享 `/tmp` 跨用户攻击、真实满盘、完整 make smoke 未跑。
- 不要误认：QML/Quick、N2 网络、PR #51/#20 挂账均与本组无关，状态未变。
