# 文件元数据 M0：契约与 ABI 占号

2026-11-13。依据 [权限与 POSIX 元数据裁决](../plans/permission_model_glibc.md)（#131）
与 #123 的执行要求。本记录只交付 M0，**不含实现**。

## 交付

- 新契约 [file_metadata_v1.md](../contracts/file_metadata_v1.md)：
  - 现状盘点（wire v2、op1–28、会话/句柄、libc 合成 0777、access 放行、
    utime/chmod/chown ENOSYS、FatFs FF_USE_CHMOD=0、双 SDK）；
  - FAT 诚实子集目标：只承诺 RDO + mtime；chown 改为不接受改值；
    stat/access 按投影与 RDO；atime/ctime 明确为 mtime 投影；
  - 线格式：保持 abi_version=2，新增 **op 29**，元数据结构放在 request.data；
    旧服务返回 invalid，libc 映射 ENOTSUP 作为能力探测；
  - 错误优先级、只读卷/写保护、unlinked/anonymous 拒绝、回滚与兼容矩阵；
  - 客体验收清单与 M1 实施步骤（含不得提前把 PL-0005 标 fixed）。
- `abi_registry.md`：files op 命名空间登记 op29 `set_metadata`（claimed，M0），
  并在待实施预分配表列出，不生成源码常量或能力声明。

## 验证

- `tests/docs_consistency.py`：passed（990 本地链接、78 syscalls、73 history）。
- `tests/abi_doc_consistency.py`：PASS（现有 syscall 与 file op 表一致）。
- 未构建/未跑客体：M0 无代码，符合“设计不等于实现”的裁决。

## 下一步（M1）

FF_USE_CHMOD=1 → 测量目录 RDO/只读卷行为 → 服务 op29 → libc 映射与 stat/access →
双 shell/双 SDK 客体验收 → 再更新 PL-0005 与 #123。
