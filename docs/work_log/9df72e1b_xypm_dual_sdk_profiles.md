# 9df72e1b — xypm 独立 newlib/glibc 候选准入

## 范围与依赖

2026-11-25，基于 PR #154 `5984573a3a4898734f10495af2d36de5ec16c0b6`，完成 G4
迁移的独立 SDK/profile 生成和核验入口。复用现有 P0/P3 格式、SDK 整树摘要、
GNU archive 解析器、严格 JSON、来源认证状态解析和原子元数据创建。

变更包括 `scripts/create_xypm_profile.py`、`scripts/xypm_sdk_profile.py`、
宿主负向测试与 [专项契约](../contracts/xypm_sdk_profiles.md)。
`xos_app.py` 增加运行库边界：现有 newlib 后端明确拒绝 glibc 候选，历史未写
runtime family 的 profile 保持既有行为。`package_p0_cases.py` 增加显式
`--profile` 参数，默认仍为原冻结 profile，便于直接复用真实 C/C++ 构建验收。

两套运行库分别绑定完整 SDK、启动对象、静态库、头、来源材料、输出、仓库和
安装盘。v1 数据库保持单 profile 校验。G3 process 库和 glibc xypm 迁移接入由
后续独立模块完成；本次没有放行旧 newlib 后端来编译 glibc 应用。

## 完成的检查

| 检查 | 实际结果 |
|---|---|
| 独立 SDK 准入宿主测试 | **39/39 PASS**；使用明确标识的合成材料 |
| 真实 preview newlib SDK 创建与复核 | PASS；C++ single 归档、libc lineage 和整树绑定 |
| 新正式 glibc C SDK 创建与复核 | PASS；glibc 2.44、完整 686 项产物、上游认证材料 |
| 既有 P0 仓库外 C/C++ 构建与打包 | **16/16 PASS**；新候选、真实交叉 GCC/G++ 与可重复 XPK |
| 既有 profile 错误诊断 | **3/3 PASS** |
| 首份正式 glibc C++ SDK 完整准入 | 拒绝：输出缺少继承的 C 来源 `source_verification` 目录；构建方修复导出流程并重新构建 |
| C++ 其余材料只读诊断 | PASS；已核完整产物、独立 GCC 签名、头/许可、归档目标及 unwinder；诊断未生成 profile |
| 修正后的 glibc C++ SDK 完整准入 | **PASS**；新输出 v2、1571 项完整产物、两套独立来源证明，正式 create/verify |
| glibc C++ 仓库外程序编译/静态链接 | **PASS**；string/vector、静态 TLS、mutex/thread、异常；客体未运行 |
| v2 组合 C++ 客体（SDK 构建分支） | **FAIL**；首次 ostream 使用出现 page fault，构造段未完整收纳；SDK 分支正在重建 v3 |
| glibc xypm 客体/混 profile 同盘安装 | 未运行；应用迁移和同盘新契约分别接续 |

39 项测试覆盖显式 family、冻结 ID、SDK/产物/manifest 改变、额外头文件、路径
越界与链接、缺 CRT、错误目标、版本不一致、认证缺失/损坏/过期、C++ 独立来源、
错误线程/include/unwinder 模型、真实归档成员摘要、弱 pthread 引用、元数据类型、
伪造客体资格、并发输入改变、排他输出和旧后端拒绝边界。测试中的合成签名状态
只用于验证解析和拒绝行为；真实签名材料来自下表绑定的已完成 SDK 构建。

unwinder 检查解析实际 ELF64 section/symbol table，要求 glibc C++ 的五项替换
成员摘要匹配，并核对强未定义 pthread mutex/once 引用。C++ 来源材料使用
`cxx/port/source_lock.json` 和独立认证 report，原 C 来源记录保持原字节。

### 真实 SDK 与产物绑定

preview 工具入口使用 release `xos-glibc-sdk-preview` 中已核对的工具环境：
GCC/G++ 16.2.0、Binutils 2.47.20260726。newlib SDK 使用 P3 真实客体模块已
组成且冻结的同一套产物，manifest 为
`af23d18248e21a85eb8392ca374a13a8f5b376eb787f342ef7ff9febc1093c4e`，newlib 版本
4.6.0.20260123。glibc C 基底是 G4 `g4_c_sdk_qualified`，manifest 为
`9ef954336bdb2b211c24a6545af2d2ace3cdec927e5d9ae167f01f9dd569363d`。

| 文件/绑定 | SHA-256 |
|---|---|
| newlib SDK 整树 | `092349e37c424fd3b800bd4bd8718ed0e01af80dc0b2563ee9c8a5e4735e9f24` |
| `build/xypm_profiles/newlib_candidate.json` | `cbdd91f4adfb64deb1ab29ab609b8263c0bade2e449eaaa02fba50f94a2a20c1` |
| glibc C SDK 整树 | `413e2dd6701914df8c698c8a10a4cba5bf6aee69026f967cdada221ec551e830` |
| `build/xypm_profiles/glibc_c_qualified_candidate.json` | `1228f3b08c696be86abfded80f985a66663c8ade367b0f8398920a995d5cc10b` |
| glibc C++ v2 SDK manifest | `9c385a5865adfc927d697227e12524d1adb72212488525c0c6f203e4bfbcdf11` |
| glibc C++ v2 SDK 整树 | `757f9b57da9ff3a911864348ac7c0488037b5bc29bdca5f3d163282e18cef609` |
| `build/xypm_profiles/glibc_cpp_v2_candidate.json` | `e9b9a92e1c145d5c869953f4d1e0f3eefe94410a7a6df813a0fd2692485e4447` |
| `build/xypm_profiles_host_final/report.json` | `b89c2eebc7e3059f07a1b92c2abdfb56ea792e05edf9223916e49c7d808e52ee` |
| `build/xypm_profiles_p0_cli/host_report.json` | `d2d8f311e10cd41ed414df961544c1afe31e3a013113670ba3084639fd1e939b` |
| newlib 仓库外 C ELF / XPK | `bc5be2cfcfde4eaa697b082cb5015c55c864532baeef12b158a8ce84f7fab87e` / `3e64848ffbdbc2f4c10263cdc4ef1d7d95f714697e55e066f114267b89eadbf9` |
| newlib 仓库外 C++ ELF / XPK | `fab96f3213698789736d72b36610613937e89d992a3eb5c0257f6ff102768c70` / `021dce30693ee11b208234289394b5aa1d5e0fa40d289c4ff666c075e966ca02` |
| glibc 仓库外 C++ ELF | `bf417e66489245ec9b4f74811405382229ab59709f8d5d85b398d0e10a16a873` |
| glibc 仓库外 C++ 程序构建记录 | `c1ed0a14d1fccb0cebaa54621f43af8c471507fc2130afec9147ce862a2789d1` |

newlib 与 glibc 候选均保留 `candidate_guest_not_run`、空
`verified_system_builds`。SDK 的既有专项客体结果按各自证据使用，生成器不会
把它转换成本次候选的新应用资格。P0 的 C/C++ ELF/XPK 产物与 receipt 保存在
`build/xypm_profiles_p0_cli/{c,cpp}`；真实编译发生在仓库外临时工程内。

## C++ 导出缺口与协调

第一份 C++ SDK `g4_cpp_qualified` manifest 摘要为
`dffc9298eb4882b67b71879c43cf70a7cc4f25d27d911eb31391a8f73103f05b`。
它继承了 C 基底的来源 report 和摘要，实际输出却只带 GCC 的
`gcc_source_verification`。完整 CLI 按契约拒绝，日志保存在
`build/xypm_profiles/glibc_cpp_initial_admission.log`。构建方接手修复为复制
经验证的原 C 认证文件，另建 `g4_cpp_qualified_v2`；等待该独立产物的过程中
继续完成其它边界检查。

为尽早识别其它导出问题，只读诊断把 C 来源的读取指向原始 C 基底，其余检查
全部使用原 C++ SDK；该诊断没有创建/核验成功的候选。记录
`build/xypm_profiles/glibc_cpp_layout_diagnostic.json` 明确标注用途和缺口。
实际通过 glibc/GCC source lock、key/signature、C++ 许可与 include 布局、
1678 个 libc、831 个 libm、147 个 libgcc、199 个 libstdc++、65 个 libsupc++
归档成员的目标检查，以及五项派生 unwinder 成员摘要和强 pthread 引用。

随后新输出 v2 正式创建与核验通过，原错误输出和诊断记录保留。仓库外实际程序
使用 [C++ fixture](../../tests/fixtures/xypm/glibc_profile_program.cpp) 的相同字节，
由 G4 程序构建器 `d4877ad597ee7b6db02839a7430ce57081ebcd3a437f3ed656b71a6758c5d207`
编译和静态链接；记录 `static_program_linked`、`guest=not_run`，没有调用 newlib
后端。源码、ELF、编译/链接日志与报告保存在 `build/xypm_profiles_cpp_external`。

G4 分支同时执行的 v2 组合客体发现独立的 CRT/linker 基础缺陷：第一项
`g4_cpp_runtime` 出现 vector 14，地址 `0xffffffffffffffe8`。负责人定位为 GCC
产生的 `.ctors/.ctors.65445` 未被当前脚本纳入 constructor array，导致早期
iostream 初始化缺失；修复由 SDK 分支完成并新建 C/C++ SDK v3。v2 的源码认证、
字节绑定和静态链接结果保留，本模块所有候选继续保持待客体验收状态，不激活 v2。
失败报告/串口原字节另保存在 `build/xypm_profiles_cpp_v2_guest_failure`，来源
系统 build ID 为 `a7a63638a077dfe4`，SDK manifest 与表中 v2 相同，摘要分别为
`41008b3e9d15a9791b0840e5c798b7adf59b43d9405eeec9a41ce11151a1bcea` 和
`d2e4a85bb3f710f748df2635bcbb78f78c144a92e870e0ce8db86cd5293c2430`。

## 复现

`XOS_NEWLIB_SDK` 指向对应完整 newlib SDK，`XOS_GLIBC_C_BUILD` 指向已完成的
glibc C build，`XOS_SDK_RUN` 指向已核验 preview 工具入口。输出目录与 SDK
分离，候选文件路径必须尚不存在。

```sh
mkdir -p build/xypm_profiles
python3 tests/xypm_sdk_profile_host.py --output build/xypm_profiles_host_final > build/xypm_profiles_host_final.log 2>&1
python3 tests/xypm_profile_errors.py > build/xypm_profile_legacy_errors_final.log 2>&1
python3 scripts/create_xypm_profile.py create --runtime-family newlib \
  --sdk "$XOS_NEWLIB_SDK" --cxx --id xos-x86_64-newlib-g4-candidate-v1 \
  --output build/xypm_profiles/newlib_candidate.json
python3 scripts/create_xypm_profile.py verify --runtime-family newlib \
  --sdk "$XOS_NEWLIB_SDK" --profile build/xypm_profiles/newlib_candidate.json
python3 scripts/create_xypm_profile.py create --runtime-family glibc \
  --sdk-build "$XOS_GLIBC_C_BUILD" --id xos-x86_64-glibc-g4-candidate-v1 \
  --output build/xypm_profiles/glibc_c_qualified_candidate.json
python3 scripts/create_xypm_profile.py verify --runtime-family glibc \
  --sdk-build "$XOS_GLIBC_C_BUILD" --profile build/xypm_profiles/glibc_c_qualified_candidate.json
"$XOS_SDK_RUN" python3 tests/package_p0_cases.py --sdk "$XOS_NEWLIB_SDK" \
  --profile build/xypm_profiles/newlib_candidate.json \
  --output build/xypm_profiles_p0_cli/host_report.json
python3 tests/docs_consistency.py --output-dir build/xypm_profiles_final_docs
python3 tests/check_public_evidence_paths.py --index --base 5984573a3a4898734f10495af2d36de5ec16c0b6
```

SDK 来源重建按各运行库构建器及源锁执行；此处的 `verify` 验证生成候选与现有
SDK 的完整绑定。glibc C++ 使用已完成 v2 输出，`XOS_GLIBC_CPP_BUILD` 指向该
build，`XOS_GLIBC_PROGRAM_BUILDER` 指向已包含 G4 支持的程序构建器脚本。

```sh
python3 scripts/create_xypm_profile.py create --runtime-family glibc \
  --sdk-build "$XOS_GLIBC_CPP_BUILD" --cxx --feature threads \
  --id xos-x86_64-glibc-g4-cpp-candidate-v1 \
  --output build/xypm_profiles/glibc_cpp_v2_candidate.json
python3 scripts/create_xypm_profile.py verify --runtime-family glibc \
  --sdk-build "$XOS_GLIBC_CPP_BUILD" --profile build/xypm_profiles/glibc_cpp_v2_candidate.json
XOS_PROFILE_PROJECT="$(mktemp -d -p .. xypm_profile_external.XXXXXX)"
cp tests/fixtures/xypm/glibc_profile_program.cpp "$XOS_PROFILE_PROJECT/main.cpp"
"$XOS_SDK_RUN" python3 "$XOS_GLIBC_PROGRAM_BUILDER" \
  --sdk "$XOS_GLIBC_CPP_BUILD/sysroot" --source "$XOS_PROFILE_PROJECT/main.cpp" \
  --output build/xypm_profiles_cpp_external/app.elf
```

glibc xypm 客体验收须等待统一 process/file 会话库和完整 SDK 的独立组合，不混入旧
newlib libxos 或私有 request-id/lock hooks。

## 证据索引

生成器只绑定外部 SDK 的原字节与认证材料，不把其它模块的 SDK 拷进本模块。
本模块的平铺索引覆盖候选、宿主报告、真实程序/包、日志和文档检查。完成上述
命令后可直接生成本次索引，文件数和摘要以输出为准：

本次按下列代码实际生成 **42** 项，核验 **42/42 PASS**；索引摘要为
`4912dffa683037ca0b7585d16b0ef7a09467e1a34f29aae5ddeda8417617747b`。
文档检查通过（1049 个本地链接、78 个 syscall 登记、73 项 history 来源）。
公开路径检查 9/9 `PUBLIC_READY`；`packages.md` 的一项 `DOUBTFUL` 经人工
核对是既有通用工程示例 `PROJECT=/tmp/xos_hello_friend`。`git diff --check` 通过。

```sh
python3 - <<'PY'
import hashlib, json
from pathlib import Path
root = Path('build')
files = {}
def add(path):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError('expected regular evidence file: ' + str(path))
    with path.open('rb') as stream:
        files[path.relative_to(root).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
for name in ('xypm_profiles', 'xypm_profiles_host_final', 'xypm_profiles_p0_cli',
             'xypm_profiles_cpp_external', 'xypm_profiles_final_docs'):
    directory = root / name
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError('evidence directory missing: ' + str(directory))
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise RuntimeError('evidence symlink rejected: ' + str(path))
        if path.is_file() and '__pycache__' not in path.parts:
            add(path)
failure = root / 'xypm_profiles_cpp_v2_guest_failure'
if failure.is_dir():
    for path in sorted(failure.iterdir()):
        add(path)
for path in sorted(root.glob('xypm_profile*.log')):
    add(path)
output = root / 'xypm_profiles_complete_index.json'
with output.open('x') as stream:
    json.dump({'version': 1, 'files': dict(sorted(files.items()))}, stream, indent=2)
    stream.write('\n')
print('indexed', len(files), 'files in', output)
PY
python3 scripts/verify_evidence_index.py build/xypm_profiles_complete_index.json
```
