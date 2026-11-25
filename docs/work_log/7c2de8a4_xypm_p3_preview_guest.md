# 7c2de8a4 — xypm P3 preview SDK 客体补验

## 范围与基线

2026-11-25，基于主线 `5e49012ab2b359b31999d78083341ede98d5de4f`。
本组复用已合入的 xypm P3 离线仓库与 P2 单包事务，补强验收入口并实际运行。
相关契约为 [xypm_repository_v1](../contracts/xypm_repository_v1.md)；
[P3 实现记录](bebd5daf_xypm_p3_offline_repositories_and_validation_audi.md)
已有主线组合的 13 项客体结果。本次保留这份历史事实，另行绑定当前输入与结果。

修改范围：`tests/boot_smoke.py`、`tests/package_p3_guest.py`、
`docs/plans/packages.md` 及本记录。未改变公共 ABI、包格式、事务实现、
已冻结 B2 profile 或单 profile 安装数据库的相等校验。

## 改动与选择

- `Guest` 提供默认开启的 `qmp_enabled` 开关；复用 glibc PR 栈已有的相同
  serial-only 行为，关闭后误调用 QMP 明确报错。P3 使用串口完成全部操作，
  `--serial-only` 允许无 Unix socket 的宿主运行真实 QEMU。
- 增加错误 lock pin、逆序依赖闭包、异 profile、索引字节变化、损坏 XPK、
  缺失已安装依赖与反向依赖删除的客体拒绝检查。
- 每条命令保存实际退出码、预期结果标记、资源数量与输出摘要。
  `maint-run` 以 supervisor 的 `maintenance: completed` 为成功证据；该标记
  仅在子进程 exited/0、必要恢复完成及维护租约释放后输出，源码为
  `supervisor.cpp::maintenance_run`。维护命令未打印的子进程退出码保持空数组。
- 首次关机和重启关机后分别用宿主后端校验数据库、归属文件和摘要；确认仅剩
  `friends.base` 的三个文件，应用已删除，15 个仓库输入保持原字节。
  最终盘摘要改为停止 QEMU 后采集，避免读取仍由客体写入的镜像。
- 验收前后核对系统源码、镜像、manifest、profile、SDK 整树、xypm 与 dash，
  检测运行期间的构建或输入漂移。原件保留在独立 `build/xypm_p3_*` 目录。

## 工具与运行库边界

使用 release [xos-glibc-sdk-preview](https://github.com/Xiao-John/XylophoneOS/releases/tag/xos-glibc-sdk-preview)
的 Linux amd64 环境：GCC/G++ 16.2.0、Binutils 2.47.20260726、NASM 3.02、
QEMU 11.1.3。工具可执行文件摘要保存在系统 manifest 中。

preview kit SHA-256 为
`20efd69b859a149ce16c86ad92ead6f64e19c0d15f395615e4cf1e44888a70f1`；
解包后 `inputs.json` 的 1080 个输入逐项通过核验。
本次 xypm 使用当前系统导出的 ordinary newlib SDK，加 preview 自带的单线程
C++ 头与库。先核对两者 newlib 版本及 `libc.a`/`libm.a` 完全相同，再复制
C++ 材料；GNU 授权文本、preview 来源说明与原始输入清单随 candidate SDK 保存。
dash 独立针对当前系统 SDK 构建，SDK manifest 与系统验收输入一致。

候选 profile 为 `xos-x86_64-newlib-single-p3-preview-v1`，输出、SDK、仓库、
测试盘均独立。`verified_system_builds` 保持空数组，具体客体资格由本次报告
绑定 profile 摘要，不在完成测试后修改 profile 字节。glibc SDK/profile 的
生成、校验及应用运行库适配在后续独立模块处理。

## 实际结果

| 检查 | 实际结果 |
| --- | --- |
| Python/原生解析器一致性 | `tests/package_p3_repository.py` 50/50 PASS |
| ASan/UBSan | `ASAN_OPTIONS=detect_leaks=0` 下 50/50 PASS |
| 默认 LeakSanitizer | 当前宿主 ptrace 限制阻断；失败日志保留 |
| xypm / dash 交叉构建 | 均完成；dash debug stripping 保持 LOAD/TLS 与入口字节 |
| P3 QEMU 串口客体 | 20 条命令 PASS，含 7 个新增拒绝检查 |
| 生命周期与资源 | 每条命令及重启后 `[129816 free_pages,2 tasks,0 completions]` |
| 停机后数据库/文件验证 | 两次 `verify-installed` 均为 3 files；base-only 状态相同 |
| 仓库输入保护 | 15 个输入文件逐项摘要相同 |
| 构建输入稳定性 | 验收前后源码、SDK、ELF、镜像、profile/manifest 全部一致 |
| 文档/ABI 一致性 | 1032 links、78 syscall 登记、73 history sources PASS |
| 公开路径检查 | 4/4 files PUBLIC_READY；既有 `/tmp` 示例的 DOUBTFUL 经人工核对为通用项目示例 |
| 平铺证据索引 | 1368/1368 files PASS |

实际命令包括 xsh 下的正确与错误仓库验证、dash `set -e` 脚本中的依赖顺序与
错误 pin 处理、无维护租约写入拒绝、依赖规划拒绝、显式 base/app 安装、app
revision 0→1 升级、应用删除及重启后的查询。资源数量来自实际内核统计。

首次新增 foreign-profile fixture 使用了只允许新建的 `write_metadata`，在
进入客体前以 `FileExistsError` 失败。改为显式修改独立测试副本后，重建系统、
SDK 绑定、xypm 和 dash，再完成上述通过结果。原失败日志与当时输入标识保存在
`build/xypm_p3_evidence/fixture_failure/`，未改写为成功。

## 输入与证据

| 对象 | 标识或 SHA-256 |
| --- | --- |
| 系统 build id | `622d5214f14e24f5` |
| 系统 manifest | `23869b108ddfc4ac46605b7089034e6fcd4157fd1b5a9537121f197b8cb314da` |
| ISO | `3fcf1b2ccdadb51736683ffd19f37956628ed244456ac8c6e02116f86023c84f` |
| candidate SDK 整树 | `092349e37c424fd3b800bd4bd8718ed0e01af80dc0b2563ee9c8a5e4735e9f24` |
| candidate profile | `ce61f970f8bd82d3ebe6fda11df527216e8578695737e33963b05c8e978fa707` |
| xypm ELF | `c7e156f6851f46e2833c25feea23e4174051fc03fa442bda4d1a51cc5b0a5043` |
| dash ELF | `0716c385f9948e29b68d1e4a3ee314b1293811bcb29c6d17a92441e5121f87c3` |
| 客体 report.json | `5accee89032b43461b466d9f68015ca4cb31d8fa46f9756ce72a461d0cfd6a7f` |
| 首次启动串口日志 | `c2206fdb71c07a45eb29f2e8827df767fcf9029ae7ea7e48e6c91693a697d0af` |
| 重启串口日志 | `2d9ffdb8fa2c11f209f76ac492609dddfa999a0b8d485eec3c9ff64a18be9696` |

目录：`build/xypm_p3_preview_system/`、`build/xypm_p3_preview_sdk/`、
`build/xypm_p3_guest_preview/`、`build/xypm_p3_evidence/`。
平铺索引 `build/xypm_p3_evidence_index.json` 使用仓库根相对路径。
索引 SHA-256 为 `59a46e0a0d0f2bc44ccd1af06c6c707f069b7a855398524b1114dbd8a25be948`。
测试盘在完成停机检查后由 fixture 删除；报告保存实际初始/最终摘要，复跑创建新盘。

## 复现

先准备 preview release 的运行入口和解包的 `linux-amd64` kit：
`XOS_PREVIEW_RUN` 指向可执行的环境入口，`XOS_PREVIEW_KIT` 指向 kit 目录，
`XOS_PREVIEW_KIT_ARCHIVE` 指向原始 kit tar.gz。以下命令从本仓库根执行。

```sh
"${XOS_PREVIEW_RUN}" python3 scripts/build.py --output-dir build/xypm_p3_preview_system
python3 tests/package_p3_repository.py
ASAN_OPTIONS=detect_leaks=0 python3 tests/package_p3_repository.py --sanitize
```

从本次正式构建准备独立 candidate；完整校验与组合步骤如下。所有输出须是新路径。

```python
import hashlib, io, os, shutil, stat, sys, tarfile
from pathlib import Path, PurePosixPath
sys.path.insert(0, 'scripts')
from xos_app import tree_receipt
from xypm_format import canonical, load_json, require, sha_file
base = Path('build/xypm_p3_preview_system/sdk')
kit = Path(os.environ['XOS_PREVIEW_KIT'])
archive = Path(os.environ['XOS_PREVIEW_KIT_ARCHIVE'])
archive_bytes = archive.read_bytes()
require(hashlib.sha256(archive_bytes).hexdigest() ==
    '20efd69b859a149ce16c86ad92ead6f64e19c0d15f395615e4cf1e44888a70f1', 'kit mismatch')
verified_kit_files = {}
with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as bundle:
    for member in bundle.getmembers():
        path = PurePosixPath(member.name)
        require(not path.is_absolute() and '..' not in path.parts
                and path.parts and path.parts[0] == 'linux-amd64'
                and (member.isdir() or member.isfile()), 'unsafe kit member')
        if member.isfile():
            name = PurePosixPath(*path.parts[1:]).as_posix()
            require(name not in verified_kit_files, 'duplicate kit member')
            verified_kit_files[name] = hashlib.sha256(bundle.extractfile(member).read()).hexdigest()
def kit_files():
    result = {}
    for path in kit.rglob('*'):
        mode = path.lstat().st_mode
        require(stat.S_ISREG(mode) or stat.S_ISDIR(mode), 'kit link/special file rejected')
        if stat.S_ISREG(mode):
            result[path.relative_to(kit).as_posix()] = sha_file(path)
    return result
require(kit_files() == verified_kit_files, 'kit differs from verified archive')
for name, digest in load_json(kit / 'inputs.json')['files'].items():
    require(sha_file(kit / name) == digest, 'input mismatch: ' + name)
metadata = load_json(base / 'manifest.json')
require(metadata['libc'] == load_json(kit / 'sysroot/manifest.json')['libc'], 'libc mismatch')
for name in ('libc.a', 'libm.a'):
    require(sha_file(base / 'lib' / name) == sha_file(kit / 'sysroot/lib' / name), 'archive mismatch')
sdk = Path('build/xypm_p3_preview_sdk')
shutil.copytree(base, sdk)
shutil.copytree(kit / 'sysroot/cpp', sdk / 'cpp')
copied_cpp = {f'sysroot/{path.relative_to(sdk).as_posix()}': sha_file(path)
              for path in (sdk / 'cpp').rglob('*') if path.is_file()}
expected_cpp = {name: digest for name, digest in verified_kit_files.items()
                if name.startswith('sysroot/cpp/')}
require(copied_cpp == expected_cpp, 'copied C++ tree differs from verified archive')
materials = sdk / 'licenses/preview_cpp'
materials.mkdir()
for name in ('GCC-COPYING', 'GCC-COPYING.RUNTIME', 'GCC-COPYING3', 'GCC-COPYING3.LIB'):
    shutil.copyfile(Path('src/ports/gcc/upstream') / name, materials / name)
for name in ('SOURCES.md', 'inputs.json', 'cpp-release-manifest.json'):
    target = materials / name
    shutil.copyfile(kit / name, target)
    require(sha_file(target) == verified_kit_files[name], 'copied material mismatch: ' + name)
lineage = {'format_version': 1, 'status': 'candidate_guest_not_run', 'runtime_family': 'newlib',
    'base_sdk_tree_sha256': tree_receipt(base)[0], 'cpp_preview_kit_sha256': hashlib.sha256(archive_bytes).hexdigest(),
    'cpp_preview_inputs_sha256': sha_file(materials / 'inputs.json'), 'cpp_source_release': 'v0.0.2-1103',
    'libc': metadata['libc'], 'cpp_archives': {name: sha_file(sdk / 'cpp/lib' / name)
        for name in ('libstdc++.a', 'libsupc++.a', 'libgcc.a')}}
(sdk / 'xypm_sdk_lineage.json').write_bytes(canonical(lineage))
profile = load_json('config/package/xos_x86_64_static_single_b2_v1.json')
profile.update(id='xos-x86_64-newlib-single-p3-preview-v1', sdk_tree_sha256=[tree_receipt(sdk)[0]],
    verified_system_builds=[], runtime_family='newlib',
    scope='isolated current-system P3 candidate; guest qualification recorded separately')
evidence = Path('build/xypm_p3_evidence')
evidence.mkdir(exist_ok=True)
(evidence / 'profile.json').write_bytes(canonical(profile))
```

```sh
"${XOS_PREVIEW_RUN}" python3 scripts/build_dash.py --sdk build/xypm_p3_preview_system/sdk \
  --receipt build/xypm_p3_evidence/dash_build_receipt.json
"${XOS_PREVIEW_RUN}" python3 scripts/build_xypm.py --sdk build/xypm_p3_preview_sdk \
  --profile build/xypm_p3_evidence/profile.json > build/xypm_p3_evidence/xypm_build_receipt.json
"${XOS_PREVIEW_RUN}" python3 tests/package_p3_guest.py \
  --system build/xypm_p3_preview_system --sdk build/xypm_p3_preview_sdk \
  --profile build/xypm_p3_evidence/profile.json \
  --xypm-build build/xypm_p3_evidence/xypm_build_receipt.json \
  --dash-manifest build/xypm_p3_evidence/dash_build_receipt.json \
  --output build/xypm_p3_guest_preview --serial-only
```

完成构建与客体后，生成本次实际输出的平铺索引，再运行核验：

```python
import hashlib, json
from pathlib import Path
root = Path.cwd().resolve()
files = set()
for name in ('build/xypm_p3_preview_system', 'build/xypm_p3_preview_sdk',
             'build/xypm_p3_guest_preview', 'build/xypm_p3_evidence'):
    files.update(path for path in (root / name).rglob('*') if path.is_file())
xypm = json.loads((root / 'build/xypm_p3_evidence/xypm_build_receipt.json').read_text())
dash = json.loads((root / 'build/xypm_p3_evidence/dash_build_receipt.json').read_text())
for name in (xypm['elf'], xypm['package'], dash['elf'], dash['debug_elf']):
    files.add(root / name)
files.add(Path(xypm['elf']).parent / 'build_receipt.json')
entries = {str(path.resolve().relative_to(root)):
    hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}
Path('build/xypm_p3_evidence_index.json').write_text(
    json.dumps({'files': entries}, indent=2, sort_keys=True) + '\n')
```

```sh
python3 scripts/verify_evidence_index.py build/xypm_p3_evidence_index.json --paths-root .
```

构建脚本打印实际 cache key；变更基线/输入后使用新打印的路径并重新构建、验收。
有 Unix socket 的宿主可省略 `--serial-only`，默认 QMP 行为保持不变。

## 缺口与后续

本次覆盖离线 P3 核心及其 P2 正常事务连接。仓库签名、可信根、密钥轮换、撤销、
防回滚、可信时间、网络下载/DNS/TLS 按既有契约继续独立实现和验收。
本次未重跑 P2 的 115 个中断点、满盘与自升级恢复矩阵；其原始结果见 P3 实现记录
及 [0066](0066_xypm_p2_validation.md)。未运行硬件/SMP/长期压力。

glibc 下的 xypm 待共享 file RPC hook、匹配的 native SDK archive、完整 glibc
C++ SDK 与独立 profile 成套构建后运行；须隔离旧 weak request-id hooks，
统一使用 glibc 的 session 锁和序号。双 profile 各自使用独立仓库与安装盘，
保留 v1 数据库的单 profile 约束。同盘混装需后续单独契约。

## PR159 评审复查（2026-11-25）

对应评论4694296468/4694296479。复现配方现在将原始archive一次读取为字节，
先校验锁定摘要，再从同一快照生成完整文件map。解包kit在复制前后均须与
该map相同，包含inputs.json本身；链接、特殊文件、路径越界和重复文件拒绝。
已实际核对1094个kit文件和当前candidate中的862个C++文件。真实反例同时
改写头文件与inputs.json，旧的内部互相校验仍通过，而新增archive绑定拒绝。

复现步骤增加实际receipt输出和索引生成代码，不依赖预先存在的本机索引。
使用既有产物执行新代码，生成新的索引后1767/1767项核验通过，原索引保留。
本增量只修文档/证据；原20项客体保持原系统、SDK和程序绑定。
结果见[评审证据](../reports/xypm_p3_review_20261125/manifest.json)。
