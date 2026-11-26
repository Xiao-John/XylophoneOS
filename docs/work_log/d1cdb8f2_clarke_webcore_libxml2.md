# d1cdb8f2 · ClarkE 的 WebCore LibXml2 前置

保留锁定 WPE 2.54.2 的 Skia 渲染设计，并用同一 glibc C/C++ SDK 对照首个
WPE headless 配置。关闭 DRM、Wayland、WebGL 和媒体特性后，上游必需包检查
仍停在目标 `glib-2.0`，当次配置未生成 WebCore 目标。两个候选构建入口共用
LibXml2、SQLite、zlib 和 ICU。 [本地视口计划](../plans/clarke_webcore_page.md) ·
[WPE 配置回执](../reports/clarke_webcore_libxml2_20261126/wpe_headless.json)

从 GNOME 公布的 SHA-256 锁定 LibXml2 2.15.4，使用保留 Linux ARM64 工具环境
的 GCC 16.2.0、CMake 4.4.5、Ninja 1.13.2 构建和安装真正静态目标库。库与
客体探针绑定同一 XOS C/C++ SDK 和 profile。仓库 CMake 发现测试确认了唯一的
目标库与目标头路径。首轮探针链接遇到 ELF 交叉编译器不接受 `-pthread`，修订为
复用目标 glibc 已提供的 pthread 接口，复建后成功。声明材料审计通过 10 项。
[目标库和链接绑定](../reports/clarke_webcore_libxml2_20261126/target.json)

QEMU 11.1.2 从 `d1cdb8f2` 重建的普通镜像 `d9bf496902de04ce` 启动。
通过 FAT 读回确认探针实际输入。合法输入覆盖 namespace、属性、分块 UTF-8、
实体解析和完整结束事件，返回 0。错误结束标签返回 2。两个进程退出后均恢复
129696 空闲页、3 个任务、1 条完成记录。当前验收是 WebCore 所用的 LibXml2 API，
完整 HTML 页面的样式、布局和像素仍按视口计划验收。
[完整验收与索引](../reports/clarke_webcore_libxml2_20261126/manifest.json)
