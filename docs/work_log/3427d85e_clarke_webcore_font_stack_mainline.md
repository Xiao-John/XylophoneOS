# 3427d85e · ClarkE 字形依赖主线复验

以 #269 合入的 `26e3d2a9` 为基线重建普通镜像 `bcb17ac93ce933bf`。
保留原先 Linux ARM64 对锁定 QtBase 6.8.3、ICU4C 79.1 和 glibc C/C++ SDK
的交叉构建。交叉工具、SDK tree/profile、源锁、编译脚本、目标夹具和 164 个目标产物
摘要均匹配。重新运行锁定 WPE 2.54.2 的 HarfBuzz 发现模块及 CMake 的
FreeType 模块，确认三个导入库均来自同一个 XOS 目标前缀。
[目标与通知复核](../reports/clarke_webcore_font_stack_mainline_20261126/target_and_license_recheck.json)

从锁定 ICU 源归档逐字节复制上游 `icu/LICENSE`，用签名指纹复验归档。
FreeType、HarfBuzz、DejaVu 的八份前缀通知和已登记的 Qt 材料逐份比对。
普通系统的许可证台账及 SDK 内十项复制材料通过仓库的材料检查。完整静态二进制的
发行审核另行验收。

客体从 FAT 启动同一原生静态字形探针，经 xsh 和 dash 各覆盖缺失字体返回 2、
有效字体返回 0 和退出后资源恢复。另从本次 QEMU 运行中的 FAT 盘快照读回探针、
字体、dash 和启动脚本，逐个对照输入摘要。两条路径都得到字形 5042、13×18 灰度栅格
和 124 个非零像素，空闲页、任务和完成记录分别还原为 129696、3、1。正常字形命令分别用时
13.307 秒和 183.562 秒。测试范围为单一 DejaVu Sans 正常样例和
文件缺失，WebCore 字体注册、WOFF2、完整 WPE/Skia 依赖和浏览器页面像素待验收。
[双入口客体与 FAT 读回](../reports/clarke_webcore_font_stack_mainline_20261126/manifest.json)

检查后续 `1c7f9abb` 合入的 Test262 与 Pumpkin 变更。普通镜像的编译命令未启用
Pumpkin 登录配置，也未编译相关变更源文件，关联头文件在该配置的条件分支内。
本次 QEMU 结果绑定 `26e3d2a9` 上构建的组合树。
