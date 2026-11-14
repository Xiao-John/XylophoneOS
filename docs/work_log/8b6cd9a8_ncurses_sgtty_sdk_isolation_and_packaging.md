<!-- coderabbit-ai-generated:v1 -->

# ncurses sgtty SDK isolation and packaging

## 范围与修改

核对并修复两条审查意见：`src/ports/ncurses/build.py` 不再向已校验 SDK 写入 `sgtty.h`。在临时 work/compat_include 中生成固定兼容头，通过 CFLAGS/CPPFLAGS 独立 include 路径供 configure、make 和消费者使用；同一文件复制到包内 `usr/share/ncursesw/include/sgtty.h`，由既有清单流程记录哈希。保持原 SDK 注册检查及收据中的 sdk_tree_sha256 语义。已有 SDK 头不影响兼容头内容；结构定义保持原配方不变。临时文件沿用 main 的 finally 清理。

新增 `tests/ncurses_build_validation.py`，模拟交叉工具及打包边界，覆盖 SDK 有/无 sgtty.h × 成功/make 失败四种场景。检查 SDK 树及收据哈希、临时目录清理、打包清单与头文件内容一致，并使用宿主 cc、-nostdinc 和仅包内 include 路径编译 term.h 依赖 fixture。

## 验证

基线 bd8ff2af46211c3a6e22a8c39c54192fddd04a99；Python 3.14.4，宿主 GCC 15.2.0。

- `python3 tests/ncurses_build_validation.py`：通过（四个子场景）。初次运行发现测试 fixture 的 tic 工具映射错误，修正后通过。
- `git diff --check`：通过。
- 实际 ncurses 交叉构建、XPK 安装与客体验证未运行：当前缺少 x86_64-elf 工具链及配置的 SDK/源码输入。模拟 pack 的结果不代表真实 XPK 验证通过。

下一步：具备实际输入后运行配方并检查真实包内头文件及消费者构建。全局 state.md 按其快照规则仅由里程碑合并者更新；本修复不更改既有客体资格。
