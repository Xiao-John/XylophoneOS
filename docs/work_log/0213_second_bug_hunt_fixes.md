# 0213 第二轮 bug-hunting：spawnp 边界、JSON INT64_MIN、diskio 回绕、注释

## 范围与结果

输入为 `CONTEST/bug-hutting-contest-4/real_bugs.md` 的三项代码缺陷和一处注释问题。
逐项修复；其中修 `posix_spawnp` 时用 255 字符路径做客体验证，发现 libc 新解析器
同一类 off-by-one 并一并修掉。

1. `posix_spawnp` 的 PATH 候选长度改为按实际是否需要 `/` 动态计算；255 字符
   （含 NUL 共 256 字节）候选不再被误拒绝。
2. `resolve_path_from` 的分量追加条件由 `>= max_path` 改为 `> max_path`：
   255 字符路径可以创建、`stat` 和 spawn，256 字符路径仍返回 `ENAMETOOLONG`。
3. `xypm_native` 的 JSON 整数逐位上限对负数使用 `INT64_MAX + 1`，接受
   `INT64_MIN`，并继续拒绝 `INT64_MIN - 1` / `INT64_MAX + 1`。
4. `fatfs_diskio` 的边界检查改为先转 64 位再相加；块循环用 `u64` 绝对扇区，
   避免 `sector + offset` 32 位回绕；`GET_SECTOR_COUNT` 在 32 位 `LBA_t`
   上限处截断而不是静默回绕。
5. `text::erase_last` 注释改为描述实际行为（不完整序列擦 0 列，无效字节按
   已回显的 1 列处理）。

## 修改文件

- `src/user/libc/newlib_syscalls.cpp`
- `src/user/programs/xypm_native.hpp`
- `src/user/services/fatfs_diskio.cpp`
- `src/user/include/xos/text.hpp`
- `.gitignore`（新增 `/blind_test/`）
- `tests/fixtures/file_posix/file_posix.c`、`tests/file_posix_guest.py`（255 字符
  PATH 分量 + 长文件名用例）
- `tests/fixtures/xypm_json/json_cases.cpp`、`tests/xypm_json_cases.py`
- `tests/fixtures/fatfs_diskio/diskio_cases.cpp`、`tests/fatfs_diskio_cases.py`

## 证据（2026-11-07）

```text
python3 scripts/build.py
Built xos-install.iso + real_mode.img | b286e58317628af4 | kernel 520272 bytes

python3 tests/file_posix_guest.py  -> PASS: 11 file posix checks
python3 tests/file_smoke.py        -> PASS: 8 E05 checks
python3 tests/runtime_smoke.py     -> PASS: 5 E08-2 groups
python3 tests/xypm_json_cases.py   -> XYPm_JSON_CASES_PASSED=7
python3 tests/fatfs_diskio_cases.py -> FATFS_DISKIO_CASES_PASSED=10
```

报告：`build/file_posix_report.json`、`build/xypm_json/report.json`、
`build/fatfs_diskio/report.json`。

## 未运行 / 限制

- 未在 `2^32` 扇区以上的真实设备上启动 FatFs；diskio 用例用桩
  `sys_block_*` 验证局部算术与截断。
- `posix_spawnp` 在树内仍无调用者；客体用例直接调用 libc，执行一个非 ELF
  长名文件，断言错误从 `ENOENT` 变为 `ENOEXEC`。
- 未重跑完整 `make smoke`；本轮跑与改动直接相关的门。

## 下一步

- `FF_LBA64=0` 仍是 32 位扇区上限；需要超过 2^32 扇区时按 0212 的 FS 债项
  一并升级，而不是只改 diskio。
- 若后续引入 `posix_spawnp` 调用者，PATH 空分量（当前按 `.` 处理）和
  权限错误传播需要单独约定。

## Git 来源

分支 `codex/bug_hunting_contest_3_fixes`，基线 `ba3d36f3`。
