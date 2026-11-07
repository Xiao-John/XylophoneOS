# 0214 第三轮 bug-hunting：XOSBND1 校验、安装器加固、host 工具缓存

## 范围与去重

输入是 `CONTEST/bug-hutting-contest-1/found_bug.md` 与
`CONTEST/bug-hutting-contest-2/found_bug.md`。两份报告大量重叠；上一轮 0212/0213
已修的项直接跳过。逐项去重后实际处理：

| 报告项 | 状态 |
|---|---|
| contest1 BUG-01 / contest2 BUG-01：成员间/尾部填充不校验 | 修复（宿主 `parse()` + 客体安装器） |
| contest1 BUG-02 / contest2 BUG-02：`build()` 不校验类型、CLI 先写后验 | 修复 |
| contest1 BUG-03：`file_ui.hpp` 声明无定义 | 已由 du4 实现，跳过 |
| contest1 BUG-04：契约 §4 仍写 type≥2 非 xpk | 修复契约 |
| contest1 BUG-05 / contest2 BUG-03：xypm 宿主缓存可预测且信任既有文件 | 修复 |
| contest1 BUG-06 / contest2 BUG-08：成员名可穿越/大小写碰撞/与 dash 目标碰撞 | 修复（生成器、解析、安装器、契约） |
| contest2 BUG-04：已存在同大小目标只哈希载荷自身 | 修复（哈希磁盘上的目标文件） |
| contest2 BUG-05：安装器只查 `reserved0` | 修复（28..63 全查） |
| contest2 BUG-06：`name_off+name_len` / `data_off+data_len` 回绕 | 修复（减法边界） |
| contest2 BUG-07：安装器不校验成员魔数 | 修复（type1/5 ELF、type2/3/4 ustar） |

## 修改内容

- `scripts/xos_bundle.py`：严格名称校验（单 FAT 文件名、DOS 保留名、尾点/空格、
  `\\ : * ? " < > |`）；大小写折叠唯一；type5 不得为 `dash`；`build()` 只接受
  1..5；`parse()` 校验所有间隙与尾部填充为 0；CLI 先 `parse()` 自检再落盘。
- `src/user/services/file_ui.cpp`：安装器做与宿主一致的名称/唯一性检查；检查
  `reserved0/1/2`（头偏移 28..63）；范围检查改减法；校验成员魔数；校验
  names→data、成员之间和尾部填充全零；已存在目标改为读取并哈希磁盘文件本身。
- `scripts/user_build.py`：`file_ui.cpp` 改用 `-Os`。安装器加固曾把内核推到 524368 字节，超过
  legacy 镜像 512 KiB 预算并停发 `xos.img`；改用 `-Os` 后为 516176 字节，两条启动路径都保留。
- `scripts/xypm_image.py`：宿主后端缓存根/摘要目录要求 0700 且属主为当前 uid，
  已有目录收紧权限、异主则回退 `mkdtemp`；源码与哈希旁文件用
  `O_CREAT|O_EXCL|O_NOFOLLOW` 写入；编译到唯一临时名后 `os.replace`；复用前校验
  文件属主/权限与旁文件 SHA-256。
- `docs/contracts/xos_bundle_v1.md`：名称规则、大小写唯一、type5 安装名约束、
  §4 魔数拒绝清单。

## 证据（2026-11-07）

```text
python3 scripts/build.py
Built xos-install.iso + real_mode.img | d1c51714a8d6d0a6 | kernel 516176 bytes | legacy=True

python3 tests/test_xos_bundle.py          -> 24 tests OK
python3 tests/xypm_host_cache.py          -> XYPm_HOST_CACHE_OK
python3 tests/iso_bundle_reject.py        -> passed（11 checks）
python3 tests/iso_bundle_install.py       -> passed
python3 tests/iso_bundle_reboot.py        -> passed
python3 tests/iso_bundle_daily.py         -> passed
python3 tests/bundle_preexisting_digest.py -> passed
python3 tests/bundle_installer_reject.py  -> bad-name / reserved1 / bad-magic 均拒绝
```

新增测试：`tests/xypm_host_cache.py`、`tests/bundle_preexisting_digest.py`、
`tests/bundle_installer_reject.py`；`tests/test_xos_bundle.py` 增加填充负例、
未知类型、FAT 名称、大小写碰撞、type5 dash 碰撞、CLI 失败不留产物等用例，并把
原本位于 `if __name__` 之后的 `BundleToolElf` 测试移回可执行位置。

## 未运行 / 限制

- 未在真实多用户共享 `/tmp` 上做跨用户攻击复现；缓存用例通过属主/权限模拟。
- 未覆盖恶意 `total`/`names_bytes` 导致的大间隙读取耗时；安装器上限沿用既有
  32 MiB 载荷预算。
- 名称规则收紧后，旧容器若含 `\\`、尾点/空格或 DOS 保留名将被拒绝；这是
  fail-closed 的格式收紧，契约 v1 同步更新，未提升版本号。

## 下一步

- 如需兼容旧容器，应先决定是否发布 v2 并对旧接受集做显式迁移，而不是放宽校验。
- 安装器仍未实现成员去重之外的安装事务回滚；安装失败可能留下已写入的前序成员
  （与 du4 既有边界一致）。

## Git 来源

分支 `codex/bug_hunting_contest_3_fixes`，基线 `ba3d36f3`。
