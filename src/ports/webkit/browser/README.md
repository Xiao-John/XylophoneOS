# ClarkE 的真实 WebCore / Qt 浏览器配置

本目录使用 WebCore 的 `TestPage`、DOM、CSS layout 和软件 Skia paint，输出
320 × 180 RGBA 页面，再由独立 Qt raster 窗口显示。页面输入上限 64 KiB；当前
验收集合为 box model、flex、grid、cascade、clip/transform 和文字。内联 CSS
由 WebCore 解释。JavaScript 和加速合成关闭，网络只由独立 broker 执行。

控制器、bootstrap、net2 policy、六维进程树预算与退出规则见
[生命周期契约](../../../../docs/contracts/clarke_renderer_lifecycle.md)。实际通过、
失败、未运行的范围见 [P1-F 工作记录](../../../../docs/work_log/478abba2_p1f_clarke_full_page.md)。
静态库或 builder 脚本的存在不代表整页客体验收已通过。

## 构建输入

所有目标依赖必须来自同一个完整 glibc C/C++ SDK/profile。源码锁分别位于
`src/ports/webkit` 的各依赖目录和 `src/ports/qt6/source_lock.json`。先完成 ICU、
FreeType/HarfBuzz、libxml2、Fontconfig、Skia raster/Fontconfig backend、WebP、
SQLite 和 OpenSSL 的目标构建。每个 builder 校验实际库、头文件和 SDK 摘要。
宿主 Qt 只提供同版本的 moc/rcc 等构建工具；目标程序不链接宿主 Qt 或 libc。

在已发布 SDK 的 shell 内使用新的输出目录，变量均指向本次实际构建结果：

```sh
python3 src/ports/webkit/page/prepare_source.py \
  --archive "$WPE_ARCHIVE" --output "$PREPARED_SOURCE"
python3 src/ports/webkit/page/build_target.py \
  --sdk-build "$CXX_SDK" --sdk-profile "$SDK_PROFILE" --prepared "$PREPARED_SOURCE" \
  --icu "$ICU_TARGET" --fonts "$FONT_TARGET" --xml "$XML_TARGET" \
  --fontconfig "$FONTCONFIG_TARGET" --raster "$SKIA_TARGET" \
  --font-backend "$SKIA_FONT_TARGET" --webp "$WEBP_TARGET" \
  --openssl "$OPENSSL_TARGET" --sqlite "$SQLITE_TARGET" \
  --output "$PAGE_TARGET" --jobs 2 --bundle-size 8

python3 src/ports/qt6/glibc/build_viewport.py --host \
  --archive "$QTBASE_ARCHIVE" --output "$QT_HOST_TARGET" --jobs 2
python3 src/ports/qt6/glibc/build_viewport.py \
  --archive "$QTBASE_ARCHIVE" --sdk-build "$CXX_SDK" --sdk-profile "$SDK_PROFILE" \
  --host-qt "$QT_HOST_TARGET/prefix" --output "$QT_TARGET" --jobs 2

python3 src/ports/webkit/browser/build_target.py \
  --sdk-build "$CXX_SDK" --sdk-profile "$SDK_PROFILE" --page "$PAGE_TARGET" \
  --qt "$QT_TARGET" --host-qt "$QT_HOST_TARGET" --openssl "$OPENSSL_TARGET" \
  --tls-origin "$TLS_ORIGIN" --tls-address "$TLS_IPV4" --tls-root-der "$TLS_CA_DER" \
  --output "$BROWSER_TARGET" --jobs 2
python3 scripts/build.py --output-dir "$SYSTEM_TARGET" --clarke-bundle "$BROWSER_TARGET"
```

WebCore 的 `--temporary-objects` 可指定当前 SDK 私有临时盘中的独立目录，以普通
自包含归档保存最终库、只临时存放可重建的对象。须维持同一 SDK 会话直到成功或
恢复失败构建；失败后用原参数加 `--resume`，每次失败记录和日志分别保存。默认
薄归档模式须保留全部成员对象。浏览器 builder 还会重新核验 WebCore 源树、生成
头文件树、归档和 TestPage 对象，不能拼接不同构建结果。

HTTPS 策略固定一个 DNS origin、一个实际 IPv4 route 和显式 DER CA，并验证
证书链、主机名和有效期。此配置没有公共 CA 仓库、DNS 或自动重定向资格。

## 客体操作与验收

系统构建只绑定三个固定 ELF 和字体的摘要。工作盘必须把 bundle 的文件按下面
位置安装；`clarke-check` 不接受由 UI 提供的程序路径或网络授权：

| Bundle 文件 | 客体位置 |
| --- | --- |
| `viewport.elf` | `/usr/bin/clarke.elf` |
| `network.elf` | `/usr/libexec/clarke/network.elf` |
| `renderer.elf` | `/usr/libexec/clarke/renderer.elf` |
| `DejaVuSans.ttf` | `/usr/share/fonts/clarke/DejaVuSans.ttf` |

由 Xsh 启动 net2 与 Interactium 后执行 `clarke-check URL`。窗口支持输入 URL、
Enter/F5 或 Go 导航、Esc 或 Cancel 取消、Ctrl+Q 退出。每次导航使用新的 broker
和 renderer；renderer 在 runnable 前已被可信控制器禁止 raw net2。页面被真正
提交到 Interactium 后才报告 `presented`。

真实验收先执行六类 DOM/CSS 夹具、几何/像素断言和错误颜色负例，再把 Qt 实际
scanout 与独立 WebCore PPM 逐像素比较。正常浏览器 runner 检查超过 16 次导航、
取消、HTTP 截断、恢复和完整 HTTPS。独立 renderer fault bundle 只在第二次
导航执行真实 trap，随后验证第三次导航恢复；生产 bundle 不含该编译分支。

```sh
XOS_QMP_TRANSPORT=pipe python3 tests/clarke_dom_css_guest.py \
  --system "$SYSTEM_TARGET" --bundle "$BROWSER_TARGET" --output "$DOM_GUEST"
XOS_QMP_TRANSPORT=pipe python3 tests/clarke_browser_guest.py \
  --system "$SYSTEM_TARGET" --bundle "$BROWSER_TARGET" --dom-results "$DOM_GUEST" \
  --certificates "$TLS_FIXTURES" --output "$BROWSER_GUEST" --mode normal
python3 src/ports/webkit/browser/build_fault_bundle.py \
  --bundle "$BROWSER_TARGET" --sdk-build "$CXX_SDK" --sdk-profile "$SDK_PROFILE" \
  --fault-navigation 2 --output "$FAULT_BROWSER_TARGET"
python3 scripts/build.py --output-dir "$FAULT_SYSTEM_TARGET" --clarke-bundle "$FAULT_BROWSER_TARGET"
XOS_QMP_TRANSPORT=pipe python3 tests/clarke_browser_guest.py \
  --system "$FAULT_SYSTEM_TARGET" --bundle "$FAULT_BROWSER_TARGET" --dom-results "$DOM_GUEST" \
  --certificates "$TLS_FIXTURES" --output "$FAULT_BROWSER_GUEST" --mode fault
```

runner 会读回安装文件验证摘要、记录实际资源与 policy occupancy，并保存失败日志。
设备首次创建 boot-lifetime reset observer 的一页开销单独记录；第二个普通设备
周期必须严格稳定，再进行浏览器测试。浏览器和服务最终退出必须回到该精确基线。
