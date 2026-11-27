# 32957274 · ClarkE WebCore 静态软件归档验收

在锁定的 WPE WebKit 2.54.2 软件图上编译完整的原生 x86-64 WebCore 静态
目标。修复 `ImageUtilitiesSkia.cpp` 对 GL 头和纹理编码的依赖，保留栅格编码路径。
为 `CustomFunctionRegistry.cpp` 显式包含 TZone 实现宏。当前 Skia 编码器能力
沿用目标库配置。

GNU patch 零 fuzz 重制源码后，逐条比较 39,117 个源码与符号链接，只有上述两个源文件
变化。原增量图达到终态后，绑定两个文件并重新核验整个有效源码树。正式 Ninja
重编两个受影响单元并完成 `libWebCore.a`，退出 0。软件图使用 GCC 16.2.0、
CMake 4.4.5、Ninja 1.13.2，原生 LLInt、无 JIT、合并单元上限 2。

此交付保留 `XOS_WEBCORE_SOFTWARE` 的显式启用方式。通过原始路径恢复
已保存的 Ninja 上层，在独立 tmpfs 校验归档与日志的 SHA-256，并确认
`ninja -n WebCore` 无工作。成员对象和归档应随同一构建图保存。

实际整页静态链接出现至少 110 个不同的未定义符号，涉及主题、剪贴板、字体、
无障碍、网络资源及音频等平台入口。链接器随后被虚拟机的 OOM 处理终止，
整页客体未运行。后续工作先落实所需的平台实现并完成静态链接，再进入 DOM、
CSS 几何和画面客体验收。完整原件与失败日志在本地恢复材料保留。

[配置、归档与链接结果](../reports/clarke_webcore_full_archive_20261127/manifest.json)
