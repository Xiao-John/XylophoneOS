# 许可证管理

2026-10-24 起，自研新代码采用 Apache License 2.0，SPDX 标识为 `Apache-2.0`。
用户口述的 APL-2.0 按此名称落实。根目录 LICENSE 保存标准全文，NOTICE 说明范围。
历史 MIT 授权不撤销：原文本保留在 licenses/mit_legacy.txt，历史文件及基线提交
记录在 licenses/legacy_mit_files.json。混合文件的旧内容保留 MIT，新贡献使用 Apache；
相应文件标为 `MIT AND Apache-2.0`，并随分发携带两份文本及归属说明。
第三方目录及独立 localpilot 项目不受这次自研许可证变更覆盖。

## 当前组件清单

机器可读入口是 licenses/components.json，记录来源、固定版本、用途、声明位置与缺项。

| 组件 | 当前用途 | 管理方式 |
|---|---|---|
| 自研 XOS/SDK/工具/测试 | 系统、SDK 和宿主工具 | Apache-2.0 新贡献；保留历史 MIT 基线 |
| FatFs R0.16 w/patch 2 | files 服务、显式离线安装器 | 原作者 ChaN 的原许可；保留源文件声明及 licenses/fatfs.txt；记录本地修改 |
| newlib 4.6.0.20260123 | SDK 头、libc.a/libm.a、libc_hello | 多来源、逐组件条款；保留 COPYING.NEWLIB 和头文件内声明，不能统一标成 LGPL 或 Apache |
| GCC/Binutils/NASM/QEMU | 当前为宿主构建/测试工具 | 安装工具不随本 SDK 打包；未来分发 Seed/运行库时另登记实际 GPL/LGPL/例外和对应源码材料 |
| GNU Binutils Seed 2.47 | 已在 XOS 验收的静态工具 | 原 GNU 条款；src/ports/binutils 保留源包锁定哈希、许可、移植补丁及构建方法，实际构建清单绑定SDK和工具 |
| Binutils 捆绑 zlib 1.3.1 | Seed 内部静态库 | Zlib 原许可保留，不是 XOS 自研 Apache 代码，不依赖宿主动态 zlib |
| GCC 16.2.0 C Seed、host libstdc++/libsupc++、GMP/MPFR/MPC | 本地客体工具闭包 | src/ports/gcc/upstream 与 source_lock.json 保留实际版本和声明；components.json 登记材料哈希；目标 E08-5 库与公开分发审查未完成 |

## newlib 与 LGPL

本仓库 COPYING.NEWLIB 开头明确说明：newlib 来自多个来源，单文件内的声明可能
优先适用。包含 BSD 类、其他许可声明，也包含 LGPL 条款。
其中第 21 节标为 `*-linux* targets only`，第 22 节标为 `i[3456]86-*-linux* targets only`；
当前库构建 target 是 x86_64-elf，不能据此把整个 newlib 都说成 LGPL。
同样，没有逐成员追溯就不能声称某个预构建库“已全部审计、只有某一种许可”。

本轮完成声明收集与分发清单，没有完成 libc.a/libm.a 每个成员到源码许可证的
映射。licenses/components.json 明确保留这个缺项。后续重新构建/升级预构建包时，
应保存源码包实际哈希、配置、必要的单文件版权声明和成员来源；不能只看项目名。

官方入口：[newlib COPYING.NEWLIB](https://sourceware.org/newlib/COPYING.NEWLIB)、
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)。
版本绑定以本仓库文件为准，官网当前文本不代替实际发布包。

## 每次引入、修改与分发

1. 引入依赖时同时记录固定版本/来源/实际哈希、原始 LICENSE/COPYING/NOTICE，
   区分运行时链接、SDK 携带和仅宿主使用。没有声明不能填“已审计”。
2. 新自研源码加 `SPDX-License-Identifier: Apache-2.0`；修改历史 MIT 文件保留
   原归属并标明新增部分/日期；修改第三方代码保留上游原条款，显式记录修改。
3. 升级依赖时比较许可文本和范围；静态链接、复制头文件、分发编译器及运行库
   各自记录，不能认为“进程隔离/静态链接/只是一个 .a”自动消除义务。
4. SDK 与发布材料必须携带 LICENSE、NOTICE、历史 MIT 和所含第三方声明。
   make build 实际复制这些材料，并在 SDK manifest 中逐文件记哈希。
5. `make license-audit` 检查登记文件/SDK 副本/新源码标识并生成清单；它是材料
   完整性检查，不是逐文件法律兼容性或预构建库全部成员的认证。
6. 未来 E08-3/4/5 分发 GNU Seed、libgcc、libstdc++ 前，按实际构建及例外收集
   所需源码、补丁、构建说明和许可。编译器的许可与它生成程序的许可分开登记。

每组交接记录许可证变化、检查结果和待办。项目仍保持轻量：一份策略、一份组件表、
实际声明文件及自动导出；不为了许可证管理建立另一个操作系统。

## GNU Seed 的当前边界

普通宿主工具与准备运行于XOS的Seed分开登记；Seed当前仅构建到忽略的缓存，
显式写入临时验收盘，没有公开发布。上游原包、XOS补丁和构建脚本共同定义
对应源码，工具manifest保留实际输入/输出哈希。自研移植新增内容Apache-2.0，
补丁引用的GNU上下文及修改后的上游文件保留适用GNU条款。
最终分发还需按实际工具/静态库成员核对完整源码材料、NOTICE/版权声明和
GCC运行库例外；不能用当前材料检查代替这一步，也不能把工具的GPL许可
自动套到仅由工具生成的普通用户程序上。

0020接收C Seed时补收GMP/MPFR/MPC实际源码内的LGPL/GPL声明，登记GCC运行库例外。
这些材料及对应源码包/补丁只构成本地来源记录，尚未完成静态归档逐成员追溯或公开
分发对应源码打包检查。原始C Seed与修复派生Seed分别保留manifest，不覆盖历史证据。
