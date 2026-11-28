# 受批准原生动态入口与 R2 客体验收夹具

## 范围与交接

生产入口及构建器 checkpoint `285d5ec2`：
`src/user/tools/dynamic_run.cpp`、`scripts/build_dynamic_launcher.py`。
独立 R2 客体夹具及构建器 checkpoint `a686ccb6`：
`tests/fixtures/dynamic_generation_probe.cpp`、
`scripts/build_dynamic_generation_probe.py`。与公共 runtime agent 协作，后者
拥有 GNU libc/libstdc++、bootstrap、共享 SDK、实际应用和最终客体 runner；
本记录不把源代码提交或 host ELF 预检写成客体通过。

`dynamic-run SLOT TARGET [args...]` 安装编译进程序的最多四个批准根，按槽
完成完整激活，再经普通 inspect/spawn/wait 入口执行目标。它继承普通
startup v1–v3 的环境、cwd、stdio 与 Files/stdio pipe 别名；terminal actor
与独立 pipe object 仍明确拒绝。公共 ABI 没有新 syscall 或结构布局。

构建器要求 C SDK manifest/tree 两个独立字面锚，完整验证/复制/复验 C SDK，
并独立绑定不可变原生系统源码、SDK 文件/目录和归档成员归属。generation
的 ID/摘要/manifest path/main path 固定在只读头中，运行时不读取相邻 JSON
扩权。完整接口与边界见 [闭包契约](../contracts/dynamic_closure.md)。

## 实际执行

在 Preview 2 SDK 中，GCC/G++ 16.2.0、GNU binutils 2.47.20260726，严格
freestanding 编译（Wall/Wextra/Werror/Wconversion/Wshadow）通过。原生系统
build ID `36d8733989de37f6` 绑定其冻结 source snapshot；C SDK 独立锚为：

- manifest `7ce5dff65e5c8b7c85fcaa730bb67a2e57a913e512e521349e2f559b8c690bc9`；
- tree `43d40911b9498895dbe67daf46e1ec9e35752b699fc1c9ff948774305d03c88f`。

初次单根 C launcher 为 123264 bytes，ELF SHA-256
`f33fe709bebafc53ae390c34f2153185038cb0e1d6d26e4bb73a3912848f07dd`。
三个根的 launcher 为 123312 bytes，ELF SHA-256
`89a425c39fc791bb30f1e8cb9d72e15708e64e822d86dd81211deec55281e40a`。
同三根 R2 fixture 为 123200 bytes，ELF SHA-256
`b061f23293ab9a77903ebcdee69d5f4127fe800db3fcd5f42d322a77986a3058`。
全部满足现有普通原生 loader 的 128 KiB 文件上限。输入不是合成主程序：
id1/2 均引用公共 GNU C stage 的真实 main；id3 的 manifest 合法，但其
main 路径故意不安装，用于验证 candidate 失败不会改写 active。

分别把 manifest 锚、tree 锚改为 64 个零，实际运行构建器，两次均在编译
前拒绝，receipt 为 failed、command 列表为空且没有 ELF。正确锚的原生
与 C SDK 快照在构建前后均通过。早期构建检查还发现本分支缺少上游
`spawn.hpp` 变更，以及内部 `thread_core.hpp` 不应被要求导出；前者导入
对应实际 source checkpoint，后者按 `user_build.py` 明确规则纠正后重建。
这些失败没有被写成工具链通过。

公共 runtime 的实际 `posix_spawn` 运行发现初版 launcher 未复制普通创建
authority：main 能运行，下一级 spawn 返回 EPERM。`3a8887aa` 给生产入口
和独立 R2 fixture 同时添加现有 supervisor 使用的
`prepare_child` / `copy_from_caller`，只继承调用者已有的权限。三者均在
Preview 2 重新构建，未覆盖旧产物或更换旧报告 hash。修复后的单根 launcher
123328 bytes / `99fa23f717346f5ecfc513bda701222468278ecd6f7deb00a637e5909c9b9b47`；
三根 launcher 123376 bytes /
`5d88ecd8fa292978feef9394e237a96e7630b2e60c637df361d086794409a008`；
R2 fixture 123264 bytes /
`d87afaf9685c89f6219a5506786ed89591008b185a4d80689a24a32395788f27`。

客体 runner 源码 `63226767` 和 SDK 路径适配 `f1c4bfc2` 保存真实 C stage 的
producer Git revision：先从指定对象库材料化原始源，再逐项匹配 stage 的
输入摘要。初次调用因 SDK 映射后 worktree 的绝对 gitdir 不可见而提前失败，
没有启动 guest；随后增加只读 `--source-repository` 参数显式指向 SDK 可见
的共享对象库。所有系统/SDK/ELF/源输入在运行前后重新核验。

构建命令模板：

```sh
python3 scripts/build_dynamic_launcher.py \
  --system "${XOS_NATIVE_SYSTEM}" --system-source "${XOS_NATIVE_SOURCE}" \
  --sdk-build "${XOS_C_SDK_BUILD}" \
  --sdk-manifest-sha256 "${XOS_APPROVED_SDK_MANIFEST_SHA256}" \
  --sdk-tree-sha256 "${XOS_APPROVED_SDK_TREE_SHA256}" \
  --generation "${XOS_APPROVED_GENERATION_BINARY}" /usr/lib/xos/generations/p0c.bin \
  --output build/dynamic_launcher
```

需要多个槽时重复 `--generation LOCAL_BINARY GUEST_PATH`；两个 digest 必须
是先前明确批准的值，不能在该命令里动态计算来替代独立锚。R2 fixture 的
helper 接收成功三根 launcher build 和同一对独立锚，单独输出新 build 目录。

## 验收范围与下一步

本组构建 receipt 的 guest 状态仍为 `not_run`，原始构建和拒绝记录导出到
[launcher 构建报告](../reports/approved_dynamic_launcher_20261128/README.md)。
R2 fixture 在一个控制器进程内执行七组检查：初始 0、保留旧 pin 激活 1、
stale 更新拒绝、失败候选保留 1、回滚 0、撤销 1 阻止新 admission、撤销
active 0 阻止新 capture。它进行四次实际公共 C main 启动，要求正确完成码，
并显式传入测试应用要求的 `DYNAMIC_ENV=verified`。

最终 native guest 和系统资源回收证据由公共 runtime runner 绑定准确
ELF/根/系统后提供；不能复用早期构建的 hash 代表后续修改。此项仍只覆盖
易失、单控制器批准集；持久防回滚、跨后代撤销与进程树预算属于 P1。

## 已完成的真实 R2 native gate

`tests/dynamic_generation_guest.py` 已实际运行两套完全分开的、准确绑定的
组合。旧 `fb881e4e` / GNU v2 连续三轮 **21/21**，四次 C 启动每轮、共
12 次，资源精确恢复 129781/2/0。随后公共 C++ 元数据性能修复重新构建
native/GNU/C stage，不能沿用旧 hash；新系统 `e8b8ba5e2645c5c2` / GNU v3 /
C stage v3 再次独立完成三轮 **21/21**、12 次真实公共 C 启动，资源精确恢复
**129779 free pages / 2 tasks / 0 completions**。

新 source 从完整冻结 `86a06b0a` 导出，只叠加五个 owned Git 原始文件，
每项来源在 `source_overlay.json`。builder 原样要求所有导出头严格一致；
没有为了迁就本工作树的旧网络头而削弱检查。C producer 为
`ba3e9d275f4b17f1fdf0ac2bbb4d79d5deae1605`，由只读 Git 对象逐文件材料化，
匹配 staged source hash；新 native SDK、C SDK、安装 ELF 与所有回执在
客体运行前后复核。新的 launcher SHA 为
`38a742644418dc0139eaefd736a68359904856c295ffb95c0483aa3ed18bdee4`，
fixture SHA 为
`9e7a0d5f60c6b84b86c68a026315963f454f0b18893308336f79428944add380`。

首轮 fixture 最后一个断言曾把“撤销 active 后没有 active”误写为 revoked；
实际返回既有 host 资格已经要求的 state。`c864db2b` 只修正测试期望，保留
失败串口/回执，不修改生产 catalog。完整成功、失败和新旧输入均在
[R2 原生报告](../reports/dynamic_generation_native_20261128/README.md)。

同时对早先两个不含宿主路径的 SDK 拒绝 JSON 做键排序，原始 input SHA
继续保留，导出表示使用独立根清单，避免把字节相同的 raw input 误认为兄弟
文件的引用；结论与数值未改。后续 G3 unsigned-mask 修复若改变公共 GNU
执行/identity/root 字节，须另验；完全相同也须给独立的字节对应记录，不
改写本次 v3 资格。下一项接 R1 frozen1024 冷启动回滚 runner 与新 fixture。

unsigned-mask 后续已建立独立映射：`b2a924c8` 真正编译 `bf8566e0` 修复后的
C 源，替换 1654 成员中的一件、保留其余 1653，partial/full GNU link 后的
安装 libc 与 C3 **逐字相同**。本工作区另核验该重建的 166 个输入和 5 个
产物、Git 原始源/脚本、C3 全部对象和三个 generation，均对应已运行的
准确 bytes。`source_byte_correspondence.json` 单独记录这一对应关系；旧
guest report、source 身份与观察值未改，未把新编译伪写为新的 guest 运行。
