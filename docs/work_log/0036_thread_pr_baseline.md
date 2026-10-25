# 0036：推送当前基线，供公共线程PR开发

2026-10-25。用户明确要求先git push，不等待Open Adventure移植。主端提交当前
已完成的公共基线；不启动线程实现、不等待游戏、不重跑旧测试或创建新Release。

## 快照范围

包含0024–0035已完成的Shell/执行诊断、dash B0/B1与sbase窄工具、UTF-8 U0/U1、
CPython PY0、包管理P0及公共线程契约，另含已进行的文档合并/历史迁移。
具体已验行为/版本各依原work_log，不把本次Git提交称为新的综合全量验收。
Open Adventure的计划可供参考；src/ports/adventure/进行中源码保留本地，不纳入
本基线，亦不删除、不回退。localpilot、缓存/SDK/镜像/凭据、AGENTS均不提交。

推送前只做git diff --check、提交文件/大小/凭据特征检查和回执源摘要核对。
当前系统回执build3d7665a665df9443，其kernel/shared/user源码及user_build.py
实际摘要与回执一致；没有重建系统或重跑UTF-8/PY0/压力。包管理P0仍以0035为准。
CPython此前尚未登记组件材料，本次从source_lock中SHA256核验过的3.14.9源码包
复制LICENSE与Doc/license.rst到port/upstream并登记components.json；没有重新许可
上游内容，没有声称完成所有静态模块逐成员审计或新二进制发布。

## 朋友接手

从GitHub main最新提交开始，按threading_contract.md v1执行T0–T2；采用1:1内核
线程/单核抢占，先生命周期再等待/单调时间及线程安全SDK。当前syscall已使用到
37（delegate）；新编号/结构/layout由PR同步共享头/SDK/文档，不按旧发行头猜测。
保持PID进程权限/会话/地址空间与TID执行上下文分离，不把TLS析构或等待做成功桩。
线程测试与ABI回执随PR；主端继续P1包管理，不并行改朋友的内核/运行库源码。
本次普通main提交/推送，不移动0.0.1标签或发行附件；实际commit和远端一致性由
Git回执确认，最终回复提供定位，避免在提交内硬填自身commit hash。

提交检查补充：189个基线路径；凭据特征/异常大文件检查未发现问题。完整
diff --check指出新纳入的上游统一补丁上下文空格/Tab，不修剪补丁内容以免改变
适用语义；排除ports补丁/原始许可材料后的普通源码/文档检查通过。没有忽略
实际编译/功能失败，也没有重新声称所有已验阶段在同一最终镜像全量复验。
