# 0066：Open Adventure 的 xypm 包化准备

2026-10-27。用户要求将已有 Open Adventure 1.12 端口包化，遵循此前“所有改动提交后
再验收”的要求。本组在独立工作区 `codex/open-adventure-package` 开展，未覆盖原工作区
输入/编辑功能的未提交改动，也未修改 xypm、内核或游戏行为。

## 已准备

- `scripts/record_open_adventure_build.py` 记录已有 ELF、生成文件、上游源包、端口
  文件和已登记 SDK 的摘要；执行环境/编译器由操作者提供，只是输入记录而非构建证明。
- `scripts/package_open_adventure.py` 接受上述回执、真实 ELF 和 SDK；核对摘要、注册
  profile、ELF 布局，以共享 xypm v1 打包器输出 `games.open_adventure`，安装路径为
  `/usr/bin/advent`；包含来源锁、构建回执、上游 BSD、XOS 和 SDK 许可材料。
- `src/ports/adventure/README.md` 记录构建输入和操作；登记 Open Adventure 原许可。
- 修复现有 `tests/adventure_smoke.py --export-elf` 的同路径复制错误；本轮未执行该脚本。

## 未完成与交接

历史 ADV0 客体报告未记录/保留 ELF 摘要和用于 xypm profile 的 SDK 身份，现有报告不能
证明现存的可执行文件来自该构建；本工作区也未找到可复用游戏 ELF。故尚未生产 XPK，
不能声称包构建、安装、卸载或游戏运行通过。未构建、未运行任何验收/测试、未发布、
未提交；无新增资格或产物摘要。打包代码及许可证登记同样尚未执行自动检查。

下一步在提交全部有关改动后，以已注册 profile 的实际 SDK 在 XOS 内按端口计划生成
`dungeon.c/h` 并编译，保留 ELF、生成文件、工具链/系统镜像和构建日志；使用记录器与
打包器生成 XPK，再以 xypm 进行校验和私有盘离线安装/卸载，启动并实际操作游戏，覆盖
负路径和回收。验证真实 SDK 与编译输入对应，不能仅靠操作者填写的回执证明；客体端
写安装仍未实现。公开分发前还需核静态运行库逐成员来源与完整许可证义务。
