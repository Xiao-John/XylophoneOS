# WebCore 的目标 LibXml2

锁定的 LibXml2 2.15.4 用上游 CMake 构建为 `libxml2.a`，装入独立目标前缀。
WebCore 的 WPE 和自定义端共享这个库。保留 SAX2、push、线程和内置编码支持，
本地页 profile 关闭动态模块、iconv 转换和 libxml2 内部 zlib，以便分别验收对应的依赖。
`LICENSE.upstream` 取自同一归档的原始 `Copyright`，锁文件记录上游公布的 SHA-256。

在提供匹配 glibc SDK 交叉工具、CMake 和 Ninja 的 Linux ARM64 宿主构建，然后用普通
XOS ISO 运行客体验收。`SYSTEM` 是从待验实现重新生成的系统构建目录。

```sh
python3 src/ports/webkit/libxml2/build_target.py --archive "$LIBXML2_ARCHIVE" \
  --sdk-build "$GLIBC_BUILD" --sdk-profile "$GLIBC_CXX_PROFILE" --output "$LIBXML2_OUT"
python3 tests/webkit_xml_guest.py --target "$LIBXML2_OUT" --system "$SYSTEM" --output "$GUEST_OUT"
```

CMake 发现测试只使用目标前缀。在客体测量 WebCore XML 路径调用的 SAX2 push 接口，
覆盖命名空间、属性、跨块文本、合法实体、错误结束标签和资源恢复。WPE 全部依赖、
WebCore HTML/DOM、样式、布局与页面像素各自验收。
