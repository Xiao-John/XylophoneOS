# ClarkE 的 WOFF 与视频位流编译

WOFF 的标准整数运算处理网络字节序，输入和目录输出均按受界字节跨度复制。
XOS 软件目标像上游 WPE 一样将视频位流头的目录加入编译搜索路径。锁定的
25 个补丁生成了新 CMake 图，2172 条 WebCore 编译命令使用该目录，仍包含原生
DNS 队列。原先失败的 AV1、VP9 和 ISO Track Encryption 编译单元及 BitReader
在实际 x86-64 工具链上生成目标对象。

在普通镜像 `8b81f5304cc1da34` 中链接和运行实际 WebCore WOFF1 转换器。
原样数据和 DEFLATE 两种输入均逐字节得到预期 SFNT，截断输入依上游契约交付空缓冲。
首次夹具采用错误的布尔语义并退出 2，原始回执仍可核查。修正夹具后的独立 Linux
QEMU 复验退出 0，FAT 回读及资源恢复均通过。

```sh
python3 tests/webkit_woff_guest.py --system "$SYSTEM_OUT" --elf "$WOFF_ELF" \
  --receipt "$WOFF_LINK_RECEIPT" --sdk-kit "$XOS_SDK_KIT" --output "$WOFF_GUEST_OUT"
```

[源码、目标对象和两轮客体回执](../reports/clarke_webcore_font_formats_20261127/manifest.json)
