# 0035：新工作盘与发行包预装 dash

2026-10-25。用户要求把可选 dash 改为预装。约束是 `xos.img` 的只读启动模块上限
128 KiB，而 dash ELF 约 976 KiB，不能放入启动镜像；本组把 dash 预装到**工作盘**
的 `/usr/bin/dash`，并保持已有日常盘不被自动修改。

## 改动

- `src/ports/dash/upstream/dash-0.5.13.5.tar.gz`：固化 261540 字节上游包
  （SHA256 `40090101…`），使离线 checkout 也能构建。
- `scripts/build_dash.py`：默认 SDK 改为 `build/sdk`；默认使用仓库内源码包；
  兼容 Python 3.9 的 tar 解包；解包后校验 `configure` 存在，避免空源码缓存。
- `scripts/install_dash.py`：把已构建 dash 离线导入指定工作盘的
  `/usr/bin/dash`；校验 manifest 的 ELF 哈希。
- `scripts/make_work_disk.py --with-dash`：仅在新盘创建成功后导入 dash；已有盘
  直接返回，不改动。
- `Makefile`：新增 `make dash`（依赖 `make build`，用当前 `build/sdk` 构建）；
  `make disk` 依赖 `make dash`，并给新盘预装 dash。
- `scripts/package_release.py`：创建发行工作盘后用发行 `sdk` 构建并预装 dash。
  当前冻结的 0.0.1-1024 没有重新打包，旧发行标签不变。

## 证据

- `make dash`：build `38c014699e36553f`，dash SHA256
  `b6763d9272bafb6bc20d7bd39666f5f885f490f07453e662ecfca5b67b7619cf`，
  991456 字节。
- 新建 512 MiB 工作盘 + `--with-dash`，启动 `build/xos.img`
  （SHA256 `d999a8ed…`）：`type dash` → `/usr/bin/dash`，`dash -i` 出现 `$ `，
  `echo PREINSTALLED_DASH` 正常，`exit` 回到 `xsh>`。
  `build/dash_preinstall_report.json` 4/4 passed。
- 已有 `work_disk.img` 未写入；`--with-dash` 在盘已存在时只打印提示并返回。

## 限制

- 旧盘不会自动获得 dash；需要显式
  `python3 scripts/install_dash.py --disk <disk>`。
- `make disk` 现在会先执行一次 `make build` 和 dash 构建，首次更慢。
- dash 仍以当前 `build/sdk` 构建；发行打包使用发行 `sdk`，两者必须同时冻结。
- 未重跑 dash A/B0/B1 全量回归；本次只验证预装盘启动和交互。
