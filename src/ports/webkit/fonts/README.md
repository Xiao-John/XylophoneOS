# WebCore 目标字形依赖

此构建从仓库已锁定的 QtBase 6.8.3 提取 FreeType 2.13.3 和 HarfBuzz 10.4.0，
通过与 ICU4C 79.1 绑定的 glibc C/C++ SDK 编译。三个静态归档安装到独立前缀，
可供上游 WPE 的 FreeType、HarfBuzz 和 HarfBuzz ICU 组件发现。

FreeType 使用上游通用文件 I/O 和随源归档提供的 zlib 代码。HarfBuzz 包含 FreeType
桥接，其 ICU 函数通过单独的 `libharfbuzz-icu.a` 接入 ICU。链接时使用输入的同一
ICU 前缀。三个字形库的构建清单绑定源材料和随前缀复制的许可证，ICU 的原始通知见
[`LICENSE.upstream`](../icu/LICENSE.upstream)。Qt 的 `BundledFreetype` 与
`BundledHarfbuzz` ABI 由 Qt 自行负责。

在提供 SDK 对应交叉工具的 Linux 宿主构建。`SYSTEM` 指向从同一提交重新构建的普通
镜像目录。客体入口另需 CMake 和 QEMU。

```sh
python3 src/ports/webkit/fonts/build_target.py --qtbase-archive "$QTBASE_ARCHIVE" \
  --icu-archive "$XOS_ICU79_ARCHIVE" --sdk-build "$GLIBC_BUILD" \
  --sdk-profile "$GLIBC_CXX_PROFILE" --output "$FONT_OUT"
python3 tests/webkit_font_guest.py --webkit-archive "$WPE_ARCHIVE" \
  --target "$FONT_OUT" --system "$SYSTEM" --dash "$DASH_ELF" \
  --dash-receipt "$DASH_RECEIPT" --output "$GUEST_OUT"
```

客体分别经 xsh 和 dash 从 FAT 打开字体，验证 ICU 字符属性、OpenType 连字与 FreeType 灰度栅格。缺失
字体返回明确错误，成功及失败后均核对资源回收。WebCore 的 FontCache 接线、颜色字形、
WOFF2、页面显示和完整 WPE 依赖闭包各自验收。
