# ClarkE 的 WebCore 本地视口

本阶段的终点是 XOS 客体从 FAT 打开本地 HTML，由锁定的 WebCore 解析并布局，
将实际页面像素交给 Qt 视口。测试文档包含一个确定尺寸的 CSS 栅格、重叠色块和
一行现有 DejaVu Sans 文本。验收分别观察 DOM 几何、已知像素位置、负向路径和退出后的
资源。`liteHTML` 样例仅供对照。

首个现场验收将 WebCore 置于无设备权限的独立用户 ELF。通过具名、有界的共享存储
或 IPC 交付 RGBA 行数据，现有 Qt/QPA 消费方校验尺寸、stride、所有权和回收。
首次可把缓冲写入客体文件用于冻结像素与比较，Qt 视口与故障恢复随后单独验收。
此路径不会引入内核浏览器逻辑。正式进程边界沿用 M2/M4 的 WebProcess/NetworkProcess 设计。

从同一 WPE 2.54.2 归档和签名 glibc C/C++ SDK 比较两个构建入口。WPE 先选上游
headless 平台、Skia 和最小的本地页面特性，实测 GLib、Soup、图形加载器及字体管理依赖。
自定义端复用 `Source/WebCore` 和随归档携带的 Skia 源，以最小 XOS 平台接线承载本地页面。
两条路径共用目标 ICU、FreeType、HarfBuzz、LibXml2、SQLite 和 zlib。源、目标归档、
宿主生成器和解析接口逐项验收，诊断性宿主试跑单独记录。

首个工作包建立可复用的目标 LibXml2，并验证 WebCore 使用的 push parser、namespace SAX 和
回收行为。接续 WPE 目标配置、真实 WebCore 生成和对象编译，以最早的可运行 HTML 页面为
目标。后端和依赖闭包的选择以实际构建推进程度和维护成本为依据。

当前客体已完成共用 [LibXml2 前置](../work_log/d1cdb8f2_clarke_webcore_libxml2.md) 和
真实 [WebCore HTML 分词](../work_log/4cc23087_clarke_webcore_html_tokenizer.md)。
WPE headless 目标配置明确停在 GLib，DOM 与整页验收尚在推进。
