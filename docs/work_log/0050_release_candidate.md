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

- 最终 build `7a4668477d7323de`，kernel 385084 字节；source commit `db5b46c`。
- `release_smoke.py` 11/11：新盘无 dash、launcher 用 install ISO、原生/SDK
  C/C++、dash C3 here-doc、Make、CPython PY3 线程/JSON/zlib/idna、xypm 查询、
  ISO 安装 dash 全文件哈希；资源 `[130272,2,0]` 前后一致。
- `license_audit.py`：7 份已登记材料通过，成员级审计仍未完成。
- `xos.img` SHA256 `f0f7360b11b018379b3e62dd6f3ca822f47af68ad72649cf69448cc7cf622d8a`。
- `xos-install-dash.iso` SHA256
  `db2f607781a7818a5238eaecb86c13d63f449383cf9a8e32be4590e83b594f12`。
- images tar SHA256
  `8dcc344f5126c2128896684455116d288d8331ca08f5d16118bf72abf7d131a8`。
- SDK tar SHA256
  `a09e6157fc5409152e2646484eb03cec5509433558734fb921d161c53365b4a1`。
- source tar SHA256
  `3f1ead9867ca567a3a1e14edd59fcbca42d238b9159c115fc96b9e7727930657`（source commit `db5b46c`）。

## 本次为通过 release smoke 做的修正

- `scripts/release_smoke.py`：原来把 `xos.img` 当作 CD 启动；改为启动
  `xos-install-dash.iso`。ZIP fixture 提供固定时间戳，避免 XOS 无墙钟下的
  `OSError`。
- `src/user/programs/supervisor.cpp`：把 `make` 与 dash 一样视为显式开发工具，
  允许其向 GCC/G++ driver 委派有限构造权；否则 release 内 `make` 的 recipe
  报 `x86_64-elf-gcc: Not owner`。
- release 镜像额外包含 sbase cat/cp/mkdir/mv/rm、make、xypm、CPython PY3
  stage 和 idna 包；这些是 release smoke 的实际依赖，不是新的 xypm 功能。

## 发布结果

- GitHub Release `0.0.1-1026` 已创建并公开，release id `423856125`。
- URL：https://github.com/Xiao-John/XylophoneOS/releases/tag/v0.0.1-1026
- 远端资产：images、SDK、source、CHECKSUMS、release_manifest；API 返回的
  SHA256 与本地一致。
- 远端 `main` 为 `16d2856`，标签 `v0.0.1-1026` 指向 `db5b46c`。
- 发布回执：`docs/releases/release_0_0_1_1026.json`。

## 未完成/待确认

- 源码尚未提交；release source materials 必须在提交后用 `git archive` 生成，
  不能拿当前包含未提交修改的工作树冒充冻结源码。
- 公开说明文案见 `docs/releases/0.0.1-1026.md`，待用户确认。
- 不修改 0.0.1-1024 资产，不提交/推送/发布。
