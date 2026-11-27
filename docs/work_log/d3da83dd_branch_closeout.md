# d3da83dd · 分支收口与组合验收

ClarkE 的底层组件和软件归档分别合入 #393、#394。真实组件客体验证覆盖共享位图、
传输授权及回收、字体、图像和网络元数据。完整 WebCore、PAL 和 JavaScriptCore
静态归档构建成功。实际整页链接显示至少 110 个未定义平台符号。补齐平台实现和
链接后再跑 DOM、CSS、绘制与清理验收。
[WebCore 归档记录](32957274_clarke_webcore.md)

固定闭包 GNU glibc 工作线程在 #392 合入。使用当前 rtld、libc 和 Net2 文件会话
完成 6 次 QEMU 冷启，覆盖 C/C++、并发、线程回收和公开动态加载拒绝。
正式运行期加载和默认 SDK 开关按各自验收执行。
[工作线程回执](glibc_d2_native_workers_current.md)

#378 的 Linux arm64 GCC Seed 完成构建、安装与路径检查。五个新建工具写入同一冻结
glibc 发行盘的副本后通过 18 项客体验收，含 xsh 和 Dash 下的 GNU Make、C/C++、
失败链接及重启。公开报告携带原件摘要。
[GCC Seed 回执](960fce43_gcc_seed_build_paths.md)

独立检出 `d3da83dd8e649e0a99d4e72f1730cf3210a6329f` 执行
`python3 scripts/build_candidate.py --output build/candidates/closeout --guest`。
得到普通候选 `91b139f2cb7b0408`，通过 79 项常规客体检查、10 项许可材料检查，
`tests/docs_consistency.py` 核对 78 个已登记 syscall。标准 Dash 安装器通过
4 项检查，ISO SHA-256 为 `b9f3cbc1b6b92415862a270cda0bd2714aeecfe101f9bdc361674f3bd8ad166a`。
