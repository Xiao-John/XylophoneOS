# bebd5daf — xypm P3 offline repositories and validation audit

2026-11-25；基线 `08f3e13ead01c0d8d7d535e9f85d7d94510c2b20`，独立分支
`codex/xypm-p3-offline-20261125`。用户授权实现 P3 网络前工作并审计相关模块，
按模块提交 PR；环境无法完成客体验收时明确缺口，由后续成员补齐。

## 本组交付

- 宿主 `xypm_repository.py`：私有副本验证后生成本地仓库，按包摘要命名；有界索引、
  profile/版本/revision/摘要精确绑定、确定性依赖锁与全闭包验证。
- 原生 `xypm_repository.hpp` / `xypm_repository_io.hpp`：复用现有有界 JSON/SHA-256/
  XPK 校验器，读取相同索引和锁，校验实际包 manifest、长度、摘要和依赖。
- 宿主 `repo-create` / `repo-lock` / `repo-verify` / `repo-plan` / `repo-install` /
  `repo-upgrade`；原生提供后四项。安装/升级显式选择锁中一个包，交给已有 P1/P2
  事务；依赖先装、反向依赖/归属/本地修改保护与维护恢复门保持有效。卸载沿用 remove。
- xypm 自身包版本和 `--version` 统一为 **0.4.0-r0**。原 builder 继承模板 0.1.0-r0，
  这会让新旧 xypm 包成为同身份不同摘要的歧义输入，现已修复。P1 guest runner 从
  验证过的实际包 manifest 推导查询期望，支持新版本。
- builder 包含两份仓库头及来源材料，缓存键绑定新增源码；SDK 打包和 smoke 清单
  包含新的宿主模块。格式 schema、用法和后续阶段见
  [仓库契约](../contracts/xypm_repository_v1.md)。

索引/锁各 1 MiB、最多 256 个索引条目、64 个选择包。拒绝缺包、混 profile、歧义身份、
冲突版本、依赖环、锁顺序改变、额外条目、摘要/长度/manifest 不符以及畸形元数据。
元数据不含可控路径；包路径由摘要构造。新代码无 newlib 私有接口，不改 syscall、
线程、TLS、VM、ELF、文件服务或 glibc 移植代码。没有新增第三方依赖。

## 审计修复及性能

1. 宿主旧 XPK 检查先 `is_file/is_symlink` 后普通 open，检查与打开间存在替换窗口，
   且零尾扫描一直读到 EOF。现以 `O_NOFOLLOW | O_NONBLOCK` 打开、fstat 核验普通
   文件，对捕获长度实行硬读取上限，并检查额外字节及实例元数据变化。索引长度来自
   这次实际验证的打开实例。保留原有 PackageError 错误契约。
2. 原生 XPK 对 header/end/member/padding 在读取前核对捕获长度，结束检查 EOF，
   拒绝文件增长及短读。P2 staging 前的 fseek 清除 EOF 状态，继续持有同一包实例。
3. 原生 payload 使用已经构建的 manifest 排序索引二分查找，保留精确大小写和重复
   拒绝。查找由 O(n²) 降到 O(n log n)，以 1027-member 包验证；没有宣称客体耗时提升。
4. `plan_package("ensure")` 已安装成功路径清空 `error_target`，避免保留已失效栈帧。
5. 依赖索引留在 JSON arena 1，锁/逐包验证复用 arena 0；选定包摘要/路径复制后才
   进入会复用 arena 1 的数据库事务，避免解析器覆盖仓库绑定。

## 已运行证据

宿主编译器为 `c++ (Debian 14.2.0-19) 14.2.0`。所有代码路径均在本分支重新运行，
未改绑任何旧冻结报告。日志和回执位于 `build/package_p3/`，不是发行材料。

| 命令 / 检查 | 结果与实际范围 |
|---|---|
| `python3 tests/package_p3_repository.py` | **50/50 PASS**；40 组相同字节分别通过 Python 和真实原生解析器；其余含 CLI、输出拒绝覆盖、真实 FatFs 单包安装/升级/卸载、反向依赖、源码替换与 builder 准备 |
| `ASAN_OPTIONS=detect_leaks=0 python3 tests/package_p3_repository.py --sanitize` | **50/50 PASS**；原生实际校验器 ASan + UBSan；报告记录该环境选项 |
| `python3 -m unittest discover -s tests -p 'package_p0_cases.py' -k PackageCases -v` | **14/14 PASS**；已有容器/路径/ELF/错误输入回归，未运行需要 SDK 的独立 C/C++ 构建类 |
| `python3 tests/package_p1_cases.py` | **12/12 PASS**；已有候选盘事务/归属/依赖/源盘不变/满盘与修改保护回归 |
| `python3 tests/xypm_json_cases.py` | **7 PASS**；原生 JSON 整数边界 |
| `python3 tests/xypm_profile_errors.py` | **3/3 PASS**；profile 诊断 |
| `python3 tests/xypm_host_cache.py` | **PASS**；私有宿主辅助器缓存 |
| 完整 `xypm.cpp` 宿主 `-fsyntax-only -fno-exceptions -fno-rtti` | **PASS**；用本次生成的 profile 头和仓库共享/用户头，不是目标链接 |
| 改动 Python 文件 `py_compile` | **PASS** |
| 文档 live links / ABI registry | **PASS**：1018 个链接、78 项登记；本组没有 ABI 分配 |
| `git diff --cached --check` | **PASS** |
| `check_public_evidence_paths.py --index --base origin/main` | **PUBLIC_READY**：19/19 文件已扫描；packages.md 既有临时示例路径标记 DOUBTFUL，人工核对为合成示例 |

完整程序语法检查命令：

```sh
c++ -std=c++17 -fsyntax-only -fno-exceptions -fno-rtti -I src/user/include -I src/shared/include -I build/package_p3 src/user/programs/xypm.cpp
```

原生普通测试程序 SHA-256：
`ef757d10a1a89fd8ec39bc2c0b8901f281f90aa2d3823890b680ae6ee80eef90`。
ASan/UBSan 测试程序 SHA-256：
`93f013ed32064119b0971b9687c0d7300d62d4cb6b14b83888ea9ab29f1bfe57`。
`report.json` / `sanitized_report.json` 记录参与实现及测试脚本的源码摘要。

独立代码审阅另对 195 个索引/锁类型和值变异作了 Python/原生差分复核，未发现接受/
拒绝分歧或异常退出；该临时审阅脚本未入提交，此结果仅为辅助证据，正式可重放门禁
使用本 PR 的 50 项套件。独立审阅提出的 xypm 包版本问题已修复并加入实际 builder
准备测试（仅替代交叉编译/打包环节，完整项目生成使用真实实现）。

## 初次提交时未运行与后续接手

- **XOS 目标构建/链接和真实 guest：NOT_RUN**。本环境缺固定 x86_64-elf GCC/G++
  16.2.0、成套冻结 SDK、QEMU；宿主原生代码测试未覆盖目标 libc/file-service/调度。
- **xsh/dash 双入口、维护租约、启动恢复、重启持久性和资源回基线：NOT_RUN**。
  新 P3 路径与 P2 故障注入/满盘/逐点中断恢复组合仍须在同一目标构建上验证。
- **LeakSanitizer：NOT_RUN**。默认 ASan 运行结束时 LSan 因 ptrace 环境终止；明确
  关闭 leak 检查后完成 ASan/UBSan，未将其写成泄漏检查通过。
- **发行 SDK 打包和 release_smoke：NOT_RUN**。只更新所需模块清单；没有发布新 SDK。
- **签名/可信根、密钥轮换/撤销、持久版本防回滚、可靠时间和网络镜像：后续阶段**。
  独立可信摘要可以绑定锁字节；发布者认证与更新安全仍需专项设计和实际验收。
- **跨包原子升级：未实现**。每次操作使用现有单包事务，精确反向依赖冲突会拒绝；
  对批量事务的 journal/恢复语义另行设计。

接手者先以匹配 profile/SDK 运行 `scripts/build_xypm.py`，保存 system/SDK/xypm ELF/
仓库/锁/磁盘摘要；按仓库契约中的命令在专用工作盘上分别执行 xsh/dash 正负例、
未授权写拒绝、依赖安装、显式升级、反向依赖拒绝、卸载、重启及 P2 故障恢复矩阵，
保存原始串口输出与资源计数。源盘使用副本，旧 P2 证据保持原适用范围。

## 组合补验（2026-11-25）

- #144 独立镜像`ea32d60cd0611de8`和 #143–#147 组合镜像
  `b097514b230c15e2`均通过 P3 客体 13 项。新鲜 FAT 工作盘验证 xsh/dash、
  无租约写入拒绝、显式依赖安装/升级/卸载、重启和资源精确恢复。
- 组合镜像 `41d313da229605c6` 的 P2 安装 34、升级 45、卸载 36 个
  故障点全部通过，满盘和自更新启动恢复通过。正式测试脚本等待维护门禁前的
  显式音频停用，并以相同服务状态比较回收资源。
- 宿主路径改为规范形后，macOS 普通和 ASan/UBSan 版分别通过原有 50 项。
  LeakSanitizer、冻结发行 SDK 打包、release_smoke、掉电和扇区撕裂未运行。
- 使用源代码匹配的单线程 SDK 与单线程 C++ 运行库生成 C3 候选 profile，
  绑定系统映像、SDK 树、ELF、dash 及工作盘摘要。冻结 B2 profile 未改变。
  组合候选的原始回执见本地 `build/pr143-147-package`；
  早期 P2 矩阵回执见 `build/final-v4-package`。
