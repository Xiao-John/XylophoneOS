# 0050：0.0.1-1026 release 候选构建与检查

2026-10-26。用户确认新 release 前先统一构建、检查许可并确定说明文案；
本组不提交、不发布，源码提交等用户确认。

## 构建

释放目录：`build/releases/0.0.1-1026`。

```sh
python3 scripts/build.py --output-dir build/releases/0.0.1-1026
cp build/releases/0.0.1-1026/manifest.json build/releases/0.0.1-1026/system_manifest.json
python3 scripts/build_dash.py --sdk build/releases/0.0.1-1026/sdk
python3 scripts/build_install_iso.py --build-dir build/releases/0.0.1-1026 \
  --dash-manifest .cache/xos_seed/dash/98d6dedee40068dd26a1/manifest.json
python3 scripts/build_sbase.py --sdk build/releases/0.0.1-1026/sdk
python3 scripts/build_make.py --sdk build/releases/0.0.1-1026/sdk
python3 scripts/package_release.py ...  # sbase/make/xypm + CPython PY3 + idna wheel
python3 scripts/license_audit.py --build build/releases/0.0.1-1026
python3 scripts/release_smoke.py
```

## 结果

- build `2e338e3d7a2adc42`，kernel 385084 字节。
- `release_smoke.py` 11/11：新盘无 dash、launcher 用 install ISO、原生/SDK
  C/C++、dash C3 here-doc、Make、CPython PY3 线程/JSON/zlib/idna、xypm 查询、
  ISO 安装 dash 全文件哈希；资源 `[130272,2,0]` 前后一致。
- `license_audit.py`：7 份已登记材料通过，成员级审计仍未完成。
- `xos.img` SHA256 `d66e1125d136aba1d89d3c0fdaac70d2d91d62f1b8ed58deec33121718e4e690`。
- `xos-install-dash.iso` SHA256
  `fde6422c0321f4e664ada7a41631db3428a090e551f51ea8932c6b8cf9dcde0a`。
- images tar SHA256
  `9a73259bbba02211d87efdeec7e1e6e4529b2a471b79022841845fbe436cf4c7`。
- SDK tar SHA256
  `efaca7984bcdef6abad460e3370e65e496e683766bb31591bd5644d1ecc3d650`。

## 本次为通过 release smoke 做的修正

- `scripts/release_smoke.py`：原来把 `xos.img` 当作 CD 启动；改为启动
  `xos-install-dash.iso`。ZIP fixture 提供固定时间戳，避免 XOS 无墙钟下的
  `OSError`。
- `src/user/programs/supervisor.cpp`：把 `make` 与 dash 一样视为显式开发工具，
  允许其向 GCC/G++ driver 委派有限构造权；否则 release 内 `make` 的 recipe
  报 `x86_64-elf-gcc: Not owner`。
- release 镜像额外包含 sbase cat/cp/mkdir/mv/rm、make、xypm、CPython PY3
  stage 和 idna 包；这些是 release smoke 的实际依赖，不是新的 xypm 功能。

## 未完成/待确认

- 源码尚未提交；release source materials 必须在提交后用 `git archive` 生成，
  不能拿当前包含未提交修改的工作树冒充冻结源码。
- 公开说明文案见 `docs/releases/0.0.1-1026.md`，待用户确认。
- 不修改 0.0.1-1024 资产，不提交/推送/发布。
