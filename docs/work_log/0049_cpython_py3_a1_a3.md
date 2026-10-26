# 0049：CPython PY3 A1 标准库闭包、A2 zlib 与 A3 离线包

日期：2026-10-26

## 结果

用户要求立即做 A1–2。A1 与 A2 均在当前正常 XOS 镜像和隔离的 2 GiB 临时 FAT32
盘上实测通过。

A1 对既有无 zlib 解释器逐项执行已知输入/操作：MD5、SHA1、SHA256、SHA3-256、
BLAKE2b 向量，HMAC-SHA256 向量，pathlib 读写、argparse 参数转换、dataclasses、
tomllib、Decimal、XML ElementTree 和带固定时间戳的未压缩 ZIP。目标进程正常退出，
回收 2864 页，资源回到`[130345,2,0]`。`statistics`在导入`random`时因系统熵接口
返回`ENOSYS`而不可用；没有添加不安全的种子回退。ZIP 测试固定时间戳，因为 XOS
没有墙钟。

A2 使用 zlib 1.3.2 官方源码包，静态构建 `libz.a`；目标 Python 配置确认
`MODULE_ZLIB_STATE=yes`，最终 ELF 内含 `PyInit_zlib`、`deflate`、`inflate`。
客体验收流式压缩/分块解压、gzip、deflate ZIP、zipimport，以及截断 zlib/gzip、
错误 Adler 校验和错误 ZIP CRC。进程正常退出，回收 2886 页，资源回到
`[130345,2,0]`。zlib 未变成动态 `.so`。

## 固定输入与产物

- XOS 正常镜像 build：`4c79f3a789dcff61`
- XOS 镜像 SHA256：`4950c4c2fb53c36ac7cf36d4b6e40954c5b36507f8fc11207b867b54520b16ee`
- Threading SDK manifest SHA256：`cdc605080f8a4c2ec28be32972c389a043491dd000c30ccfa09875f70be56d06`
- zlib 1.3.2 官方源包 SHA256：
  `d7a0654783a4da529d1bb793b7ad9c3318020af77667bcae35f95d0e42a792f3`
- zlib XOS patch：`src/ports/cpython/zlib_patches/0001_xos_errno_header.patch`
- zlib 构建 fingerprint：`cbc19df997a4ab9d6acf`
- `libz.a`：155598 字节；SHA256
  `61a50e3880c1805b9ac0eaee832052e9e5f2bb386481599995637f149619d1d0`
- CPython fingerprint：`2b6c1342ebe6fb8c22dc`
- profile：`py_t3_static_gil_pthread`
- 未剥离 `python.exe` SHA256：
  `15bd7112ad4ab4aa62714f889ae5b8e3095ad14acb7953544155c4817fab9186`
- PY3 stage：561 文件；清单 SHA256
  `19dce337e37b2d6eed07b60ad43e0de53c3b3dd2134250902d42c77c703816b5`
- Stage 同时携带 `/usr/share/licenses/zlib/LICENSE`，SHA256
  `e32ff4e00d9d94930537635291da39e7e612703334bf6fde8c7f1686fe8a45a2`

## 报告

- A1：`build/cpython_py3_a1_report.json`，SHA256
  `3150d98c1f9f1957e345660345449b6aac3bb3e14c2b3b21b0bae7c67cc98ffe`
- zlib 构建：`.cache/xos_seed/cpython/zlib/cbc19df997a4ab9d6acf/report.json`，SHA256
  `f57145e4969c88343c53ea0996df3a221670afa587ad5a667e8ef1b9da5133ce`
- A2：`build/cpython_py3_a2_report.json`，SHA256
  `e3684dc6085526be67c0a452a9cb29e399fd10159f9ffe2de3d6065202d8c503`

## 修改范围

- `scripts/build_cpython_zlib.py`：校验上游包/许可，隔离编译静态库并记录指纹。
- `scripts/build_cpython.py`：可选 `--zlib-prefix`，把 zlib 源、库和报告摘要绑定到
  CPython fingerprint 与静态链接配置。
- `scripts/stage_cpython.py`：新增 PY3 stage profile，清单包含 zlib 许可和依赖摘要。
- `src/ports/cpython/zlib_lock.json`、`zlib_patches/`、`upstream/zlib-LICENSE`。
- `tests/cpython_py3_a1_smoke.py`、`tests/cpython_py3_a2_smoke.py`及对应 fixtures。
- `licenses/components.json`、许可证说明、CPython计划/端口说明、PY3分档与状态。

没有修改内核、公共 ABI、libc/files、dash、xypm 或其他用户态端口；没有使用日常
工作盘，也未发布二进制。

## 后续与边界

- A1/A2 不提供安全熵或墙钟；`statistics`、默认 `random` 初始化仍可能被熵阻塞，
  普通 ZIP 写入需调用方提供时间戳。
- zlib 源归档保存在本机忽略缓存中；未来二进制分发须附带与锁定包匹配的源码及
  XOS 补丁。组件表和 stage 已保留原 Zlib 许可文本。
- A1/A2 后的计划顺序为 A3；本记录末尾补记了 A3 完成证据。

## A3 补充：idna 3.20 离线纯 Python wheel

A3 用 idna 3.20 的官方 `py3-none-any` wheel 验证最小离线包通道。wheel SHA256
`ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c`，BSD-3-Clause
许可原文 SHA256 `1a9a4f0e3d479a27240ddd59a9137a66ab4a0f9dfdc8ca6188cc0bfd85187f04`。
锁文件为`src/ports/cpython/idna_lock.json`。生成的 XPK 包 ID `python_idna`，SHA256
`eb8e719a849886794b1a8a3ce7d857355630d68feb94010b2148f1907e5f85f2`；按
`xos-x86_64-static-single-b2-v1` profile 校验通过，包含16个payload文件、许可和
哈希绑定的构建回执。

`scripts/xypm_python_wheel.py`仅接收锁定 wheel，校验SHA256、纯标签、成员路径/类型、
RECORD中每项SHA256与大小及保存的上游许可；拒绝路径穿越、符号链接、原生模块、
可执行文件和`.pth`。安装仅投影到 CPython 3.14 `site-packages`。它保留 wheel 的
`entry_points.txt` 元数据，但不生成 `/usr/bin` 命令。

使用PY3 561文件 stage、当前正常系统镜像 build `4c79f3a789dcff61`，在独立2 GiB
FAT32候选盘执行 xypm 离线安装，再在XOS客体导入idna并验日文域名IDNA编码/解码与
非法码点拒绝；目标进程退出0，回收5572页，资源恢复`[130345,2,0]`。随后xypm卸载：
安装索引为空且包源码/许可路径均不存在。错误wheel哈希与添加`.so`成员的wheel均在
打包阶段拒绝；输入候选盘哈希保持不变。

- A3报告：`build/cpython_py3_a3_report.json`，报告文件SHA256
  `e1130cb5fe3e030c4656be0bf1473f0a59a58c18e356848550a0445d911d24b8`。
- 生成包：`build/cpython_py3_a3/idna-3.20.xpk`；只作为本地可重建验收产物，不进入
  发行包。Wheel保存在忽略缓存`.cache/xos_seed/cpython/packages/`。
- A3首版只覆盖单个固定wheel、离线转换和xypm候选盘安装/卸载；无依赖求解、在线pip、
  venv、源码构建、console-script生成或原生wheel。后续若要扩展，按朋友实际要用的包
  再增加，而不是先实现通用pip。
- 实际命令：`python3 scripts/xypm_python_wheel.py <locked-wheel> -o <package.xpk>`、
  `python3 scripts/xypm.py verify <package.xpk> --profile config/package/xos_x86_64_static_single_b2_v1.json`、
  `python3 tests/cpython_py3_a3_smoke.py`。A3报告5项全通过。
- 未执行全量系统重建。`python3 scripts/license_audit.py`未通过：当前
  `build/sdk/licenses/components.json`副本仍绑定旧组件表摘要，和本组新增idna登记不一致；
  没有覆盖共享SDK或dash使用的build。下一次正常SDK构建应刷新SDK许可副本后重跑审计。
- 回滚验收采用xypm只读查询确认包索引为空，并用只读FAT后端确认包源码与许可路径消失；
  没有把卸载后的客体二次import作为通过证据。
