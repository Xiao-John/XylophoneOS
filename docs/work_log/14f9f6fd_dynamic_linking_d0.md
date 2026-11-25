# D0 原生动态链接：设计、源码核对与后续 gate

2026-11-25。基底 `5984573a3a4898734f10495af2d36de5ec16c0b6`（PR #154），
分支 `codex/dynamic-link-d0-contract-20261125`。本组交付独立设计 PR，由主 agent
汇总共享状态；不改 `state.md`、共享头、SDK、内核、装载器或现有验收记录。

## 完成内容

- 新增 [D0 契约](../contracts/dynamic_linking_d0.md)，定义原生动态 identity、
  解释器和完整 DSO 闭包的信任来源、版本/搜索/环境政策、pin 与不可变 generation。
- 推荐无 libc 原生 bootstrap 在自己的高匿名 arena 装载真实 glibc rtld/PIE/DSO；
  明列 load bias、PIC/相对距离、TLS、权限与实际 GCC 输出的 D1 实测要求。
- 说明当前 sys17 构造映射和 sys67 匿名 VM 的边界。高地址路线失败时，先按
  C20 论证通用 image-protect/构造映射机制，再推进低窗方案。
- 划清原生 start/exec 提交、动态 ready 与提交后故障；要求真实超时、取消、故障
  状态和逐类资源回收。新 identity/加载描述/ready/error 只有逻辑语义，D1 实施
  解码器前须登记实际 ABI，不占号、不借用保留字段。
- 固定首批完整初始闭包、eager binding、W^X/RELRO 与保留至进程退出的 DSO；
  多模块 TLS、初始化、C++ unwinder、活跃 peer exit、后续动态加载分别验收。
- 在 [glibc 勘查计划](../plans/glibc_port_scout.md#动态链接明确目标与独立验收)
  加入契约入口。设计门槛与源码事实分开记录，现有静态准入继续拒绝动态 ELF。

## 设计依据与实际差距

已核对宪法 C01/C09/C16/C20/C22/C25/C31、Discipline、ABI 登记、原生装载、
线程/静态 glibc、文件身份与 xypm P3 契约。基线源码核对覆盖 19 个文件，
锁定 glibc 2.44 归档只读核对 8 个成员，未抽取执行代码或修改归档。

关键判断：现 loader 限 ET_EXEC，拒绝动态标签；sys17 仅 owned building
低窗映射。sys67 已有高匿名 reserve/commit/protect，不能把它当作文件 mmap
或低窗 RELRO。SHARED 的 `dl-sysdep.c` 仍报错，静态 CRT 的 auxv 不能直接作为
动态启动 ABI。路径认证必须延伸到同一 pin 的实际字节，当前 P3 候选与源签名
不能自动生成完整闭包的执行信任根。

依赖安装顺序与 ELF 符号作用域分开；保留上游闭包内的正常符号抢占语义，关闭
环境驱动注入。构造优先级只在相应对象内按实际数组处理，DSO 初始化/析构按
真实上游契约验证。完整 SDK/对象摘要存外部激活记录，避免循环自哈希。

高匿名 arena `[0x100000000000, 0x200000000000)` 可用于后续研究，实际地址
范围、load bias、PIE 和 rtld 重定位能力留给 D1。启动有限等待必须有自己的
通用机制；sys51 exit deadline 和 sys62 维护屏障均不充当启动 watchdog。
用户回调之后的副作用没有事务回滚；exec 提交后失败终止新映像并公开真实状态。

官方资料已读取 System V gABI 装载/动态链接页面及 GNU 动态链接加固手册快照，
地址见契约参考节。GNU 常规手册入口请求超时，改读官方 sourceware 快照并与
锁定源归档的 `manual/dynlink.texi` 对照。x86-64 psABI 官方入口已检索，PDF
获取遇到不支持的内容类型；完整 relocation/TLS 表核对留给 D1，未记作通过。

## 实际验证与证据

工具：Python `3.12.14`、Git `2.56.1`。本组只有设计和只读源码审计，没有交叉
构建、镜像构建或 QEMU 动态执行。D1–D4 的身份解码、真实共享构建、高地址
执行、RELRO 异常、TLS、C++、资源回归、升级/撤销全部标记 **未运行**。

证据目录 `build/d0_evidence/` 包含源码输入核对、文档检查和公开路径扫描；
平铺 `manifest.json` 覆盖所有报告，校验回执写到目录外避免自引用。
完整源归档 SHA-256：
`37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667`。
归档来源认证沿用 PR #154 的源锁与签名验证，本组只检查同一归档字节并读取源码。

实际结果：`docs_consistency` **通过**（1,062 个本地链接、78 个已分配 syscall、
73 份历史来源）；暂存差异公开路径扫描 **3/3 PUBLIC_READY**，无发现；
`git diff --cached --check` 通过。平铺证据核验 **4/4 PASS**，清单 SHA-256
`b4e761d511d6c750e87d0e092ad226be101fbb66a8ddbc8ebc29fd0e8f64df16`。
这些结果覆盖设计资料与源字节核对；动态运行 gate 的状态保持未运行。

### 可复现命令

在本分支的新工作区仓库根执行，保留已有工作区的冻结原件。
`XOS_GLIBC_ARCHIVE` 指向上述已验证归档；源码核对只读
tar 成员，保留路径、大小和摘要，不运行或抽取上游程序。不同宿主的工具版本
会如实进入自己的报告，不改写本轮原始报告。

```sh
: "${XOS_GLIBC_ARCHIVE:?set the verified glibc archive path}"
python3 - <<'PY'
from pathlib import Path
import hashlib, json, os, platform, subprocess, tarfile
base = '5984573a3a4898734f10495af2d36de5ec16c0b6'
paths = [
    'src/user/loader/elf.cpp', 'src/user/loader/load.cpp',
    'src/shared/include/xos/process_abi.hpp', 'src/shared/include/xos/vm_abi.hpp',
    'src/shared/include/xos/thread_abi.hpp', 'src/kernel/arch/x86_64/tasks.cpp',
    'src/kernel/core/anonymous_reservations.hpp',
    'src/ports/glibc/crt/start.c', 'src/ports/glibc/crt/user.ld',
    'src/ports/glibc/sysdeps/xos/dl-sysdep.c',
    'src/ports/glibc/sysdeps/xos/mmap64.c', 'src/ports/glibc/sysdeps/xos/mprotect.c',
    'src/ports/glibc/sysdeps/xos/xos_vm.h',
    'src/ports/glibc/sysdeps/xos/ldsodefs.h',
    'src/ports/glibc/sysdeps/xos/shlib-versions',
    'src/ports/glibc/source_lock.json', 'docs/contracts/file_identity.md',
    'docs/contracts/xypm_repository_v1.md', 'docs/contracts/abi_registry.md',
]
files = {}
for name in paths:
    data = Path(name).read_bytes()
    assert data == subprocess.check_output(['git', 'show', base + ':' + name]), name
    files[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
out = Path('build/d0_evidence')
out.mkdir(parents=True, exist_ok=True)
report = {
    'status': 'read_only_source_audit', 'base_commit': base,
    'python_version': platform.python_version(),
    'git_version': subprocess.check_output(['git', '--version'], text=True).strip(),
    'dynamic_guest': 'not_run', 'files': files,
}
(out / 'repository_inputs.json').write_text(json.dumps(report, indent=2) + '\n')
archive = Path(os.environ['XOS_GLIBC_ARCHIVE'])
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
assert digest == '37f600f2bef3c5e8300147059568b2a2e40a7ad6ccc65ce942556d49429cc667'
names = ['manual/dynlink.texi', 'elf/dl-map-segments.h', 'elf/dl-deps.c',
         'elf/dl-tls.c', 'elf/dl-init.c', 'elf/dl-fini.c', 'elf/dl-reloc.c', 'elf/rtld.c']
files = {}
with tarfile.open(archive, 'r:xz') as source:
    for name in names:
        member = source.getmember('glibc-2.44/' + name)
        assert member.isfile(), name
        stream = source.extractfile(member)
        assert stream is not None, name
        data = stream.read()
        assert len(data) == member.size, name
        files[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
report = {'status': 'read_only_source_audit', 'archive': archive.name,
          'archive_sha256': digest, 'files': files}
(out / 'glibc_inputs.json').write_text(json.dumps(report, indent=2) + '\n')
print('read-only input audit:', len(paths), 'repository files;', len(files), 'glibc members')
PY
python3 tests/docs_consistency.py --output-dir build/d0_evidence
git add docs/contracts/dynamic_linking_d0.md docs/plans/glibc_port_scout.md \
  docs/work_log/14f9f6fd_dynamic_linking_d0.md
python3 tests/check_public_evidence_paths.py --index \
  --base 5984573a3a4898734f10495af2d36de5ec16c0b6 \
  > build/d0_evidence/public_paths.json
git diff --cached --check
```

完成上述检查后生成平铺清单，再核验：

```sh
python3 - <<'PY'
from pathlib import Path
import hashlib, json
root = Path('build/d0_evidence')
files = {}
for path in sorted(root.rglob('*')):
    if not path.is_file() or path.name == 'manifest.json':
        continue
    assert not path.is_symlink(), path
    files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
with (root / 'manifest.json').open('x') as output:
    output.write(json.dumps({'version': 1, 'files': files}, indent=2) + '\n')
print('indexed', len(files), 'evidence files')
PY
python3 scripts/verify_evidence_index.py build/d0_evidence/manifest.json \
  > build/d0_evidence_verification.json
```

## 后续顺序

先在新动态专属 SDK 分支产出真实 rtld/PIE/DSO，扫描标签/重定位/TLS 模型和预算；
据此登记 native identity、加载描述与 ready/error 的 wire 接口。以 D1-C 验证
高地址实际执行和权限转换，再接 D1-A/B/D 认证、竞态与故障闭环。任何必要
通用 VM/等待机制独立说明现有机制为何不足后实施，不从文档路线推定已经可用。

G3 正常 exit、共享文件会话、进程 FD 继承和 G4 C++ 静态 SDK 在其他独立 PR
继续推进；D0 不重做这些实现。与后续基线整合时重核接口和证据。动态可用性
最终依 D1–D4 分阶段真实验收，默认 SDK 迁移仍按原计划执行。
