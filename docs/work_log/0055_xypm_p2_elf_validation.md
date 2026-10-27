# 0055：xypm P2-2客体ELF布局校验

日期：2026-10-26。接续0051，补齐客体与宿主包校验器在 executable ELF布局检查上的差异。
本记录不是P2-2验收通过声明。

## 实现范围

- 客体在流式校验payload摘要后，对`role=executable`成员按包内偏移读取ELF头和程序头；
  不提取到文件系统，也不执行payload。
- 校验ELF64 little-endian、x86-64 ET_EXEC、程序头表边界及数量、PT_LOAD/PT_TLS边界与
  权限、地址和对齐、页映射重叠、静态TLS模板包含关系、入口点及装载/主栈页预算；其
  规则与宿主`scripts/xypm_format.py::inspect_elf`一致。
- 修改`src/user/programs/xypm_native.hpp`与`docs/package_management.md`。新增实现延续
  Apache-2.0声明；没有新增第三方依赖或ABI。

## 构建证据

使用冻结profile `xos-x86_64-static-single-b2-v1`及SDK
`.cache/xos_seed/xypm_sdk/single_b2_v1`：

```sh
python3 scripts/build_xypm.py --sdk .cache/xos_seed/xypm_sdk/single_b2_v1 --profile config/package/xos_x86_64_static_single_b2_v1.json
git diff --check -- src/user/programs/xypm_native.hpp
```

原生编译和打包成功，cache key `7247032b2da0165bcbb6`，包摘要
`98da85667d646bcadb6e6c86e375de2f05a6aaf7e1331d1109749de94bcbf3ee`，36个文件；回执状态
`packed_guest_not_run`。产物位于`.cache/xos_seed/xypm/7247032b2da0165bcbb6/`。

## 未运行与下一步

未运行guest命令、畸形ELF/XPK与数据库共享夹具、完整系统构建或许可审计，因此尚无客体
行为证据，P2-2仍未关闭。下一步补宿主/客体共用的有效与畸形输入夹具，并在隔离盘执行
verify及plan install/upgrade；之后再依据这些门禁进入P2-3持久事务恢复。
