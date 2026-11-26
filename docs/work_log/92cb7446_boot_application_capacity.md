# 92cb7446 · 冷启动的应用进程容量候选

基于 `7c581be6`。`run` 的既有合同是启动真实调度与 IPC 演示。探针和
退出示例结束后，四个持续演示任务与 Xsh、files、audio 仍占七个进程槽。
内核共有八个槽。若第一个外部命令是 dash，dash 能占最后一个槽，首次
外部子命令则可能在 `sys_process_create` 得到资源不足并以 `EAGAIN`
返回。[独立 SDK 验收](https://github.com/Xiao-John/XylophoneOS/pull/250)
记录了该失败及同镜像的 `demo quiet` 成功对照。

普通构建入口现可选择 `--quiet-demos-on-launch`。候选由 Xsh 在找到可
执行外部文件之后、分配子进程之前调用已有的 `quiet_boot_demos()`。底层
仍由原监督器授权的 kill 路径同步回收四个具体启动演示任务。`demo keep`
优先，`demo quiet` 继续立即停止；`run` 仍启动完整演示。无效路径可以在
演示运行时正常报错。配置记录在候选镜像 manifest。

```sh
python3 scripts/build.py --output-dir build/control
python3 scripts/build.py --quiet-demos-on-launch --output-dir build/application-launch
python3 tests/quiet_demos_on_launch_guest.py \
  --system build/application-launch --control-system build/control \
  --sdk-app-evidence "$sdk_selection_evidence" \
  --dash "$dash_elf" --dash-receipt "$dash_receipt" --output build/launch-guest
```

## 正常镜像和实客体回归

从相同提交建立两个正常镜像，候选 manifest 启用 `quiet_demos_on_launch`。
QEMU 的四个冷启动各用私有 FAT32 工作盘。dash 取自 #231 的真实构建，应用
是独立 SDK 选型验收生成的 glibc C/C++ ELF，均逐一与链接回执核对。

| 路径 | 客体结果 |
| --- | --- |
| 默认对照，首命令 dash | `run` 启动八项，Xsh 交互时剩七项。dash 占最后一个槽，首个外部子命令报 `EAGAIN`，dash 退出 126。退出后仍是 129654 空闲页、7 个任务、1 个完成记录。 |
| 候选，Xsh 直接启动 | 无效路径报错时四个演示仍在。显式 C ELF 命令先回收 PID 1–4，再启动程序并读取真实用户文件。接着启动 C++ ELF，线程 join 和异常处理通过。两次均退出 0，恢复到 129698 空闲页、3 个任务、1 个完成记录。 |
| 候选，首命令 dash | PID 1–4 全部回收后才出现 dash 的装载事件。脚本按 PATH 启动 C、按显式路径启动 C++，两者真实运行并返回成功，dash 退出 0。后续独立 C++ 也回到 129698/3/1。 |
| 候选，显式演示 | `demo keep` 后观察真实 IPC `ping`，直接运行 C 后四个演示仍在，资源回到 129654/7/1。`demo quiet` 回收四项，再次执行提示已停止。随后 dash 的两个外部程序均成功，回到 129698/3/1。 |

两份镜像配套 SDK 的 `libc.a`、CRT 和链接脚本字节相同。`libxos.a` 和
`libxos_loader.a` 去除调试段后逐字节一致，已定义的全局符号列表一致。
调用者仍经现有监督器/ELF 入口与进程准入。该候选可与既有镜像并行部署。

| 输入与回执 | SHA-256 |
| --- | --- |
| 默认对照 `2cc6379064949892` manifest | `14ec8f29c0bb33061d05b388d5bfd2329720a4738813063174af1ce3f3bbdac2` |
| 默认对照 ISO | `0e8490e20687f8f7d3c35e1e5952af4c4979b229a7b63e755b021b76d380676e` |
| 应用候选 `650a1cff42c3774f` manifest | `c142cd820f7e74800626ea9d4a0ecf8d99407ea499e4141941720558042a442c` |
| 应用候选 ISO | `003738b267efd04cfc770f4d248f34228f048ad5defada26d041cb2050bca913` |
| 四轮客体回执 | `3b8bbd02173ffad8c1131cc07d351122ef4ba65d93e78272f6a4efa9f275afcf` |

## 含 Pumpkin 登录主线的复验

在 `24a9aead` 上解决构建脚本冲突，保留 Pumpkin 操作员登录与普通 Xsh
应用配置各自的调用入口、构建标识和 manifest 字段。普通 Xsh 的配置与需要
独占测试 supervisor 的组合仍由原校验拒绝。

以发布的源码 `09fb69f65cf4e80ddc3cb464e81ae626e8c73d3c`（Git 树
`4efd0d9d27f66eb821f6d3a79a141d48aec439ee`）在 Linux 下重构两份镜像
并运行上表四次客体检查，四次均通过。默认对照为 `7f8256e833428fa8`，
应用候选为 `92268a76ecdcb37c`。同时选择 Pumpkin 操作员测试配置和普通 Xsh
应用配置得到预期的命令行拒绝。镜像与回执摘要如下。

| 输入与回执 | SHA-256 |
| --- | --- |
| 默认对照 manifest | `e1ae362c8ac8446efec298248251ec08a31b043eeb171d3ea228aad775b8cea8` |
| 默认对照 ISO | `6620da4df3ef70db5646ee2493b877b2dd06930ecc6d40f787ab447887e53b4b` |
| 应用候选 manifest | `2b788e1cd6c60ac292d74f035ca693e0748e845959ef1135742ca58288e628ca` |
| 应用候选 ISO | `e5f54a5da1bfb362a5b4820ba030e47af834c582b99a3a741e63b720b6269c21` |
| 四轮客体回执 | `56ba2462fb3f86ca86f90d960a16576cec097b2567b31c3e58d8c4a38965d6db` |
