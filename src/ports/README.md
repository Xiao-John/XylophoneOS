# src/ports：第三方移植目录

这里存放**第三方源码的移植元数据**，不是源码镜像，也不是 OS 功能代码。
权威规范见[端口规范](../docs/ports.md)；本文件只给目录契约和上手步骤。

## 目录契约

```text
src/ports/<id>/
  port.json           # 机器可读元数据；唯一必需文件（本规范适用）
  README.md           # 范围、状态、构建/安装/验证、已知限制（四节）
  source_lock.json    # 需要上游锁定时必需
  patches/            # 0001_topic.patch；可空
  build.py|build.sh   # 可复现配方（status ≥ cross_built_guest_not_run 时必需）
```

`<id>` 用 snake_case；`_template/` 与 `_` 开头目录被校验器忽略。不带 `port.json` 的
历史目录（`dash`、`qt6`、`cpython` 等）仍按各自 README 维护，迁移表见规范第 9 节。

## 新增一个端口

1. `cp -r src/ports/_template src/ports/<id>`；
2. 填 `port.json`（字段与取值见[端口规范](../docs/ports.md#2-portjson-字段)）；
3. 上游归档放 `.cache/xos_seed/` 或仓库外目录，**不入 git**；
4. 写 `README.md`：状态、构建命令、包 ID/哈希与安装验证命令、已知限制；
5. 写离线配方：只读 `XOS_SDK` / `XOS_SOURCE_ARCHIVE` / `XOS_OUT`，产出 `.xpk` 与回执；
6. 跑 `python3 scripts/ports.py check src/ports/<id>`，再按状态升级证据。

## 现行边界

- 端口默认**只在客体侧交付**：产物经 `.xpk`/xypm 安装，不进内核、不进启动镜像清单。
- 端口不得要求修改 `src/kernel`、`src/user`、`src/shared`；确需 OS 改动的，先按宪法走
  ABI/契约流程，端口侧只记录依赖。
- 校验器只做结构与一致性检查（字段、锁文件形状、补丁格式、证据路径、profile 存在性），
  不构建、不联网、不执行配方。
- 样例：[`nasm/`](nasm/README.md)（零补丁、autotools、guest-only、客体实测）。
