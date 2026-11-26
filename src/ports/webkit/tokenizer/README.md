# XOS 的 WebCore HTML 分词探针

用锁定 WPE WebKit 2.54.2 的原始 `HTMLTokenizer`、实体解析、实体搜索、
`SegmentedString` 及上游生成器构建目标探针。复用同一 glibc C/C++ SDK、
ICU 和已经编译的 JSC 静态配置、WTF 与 bmalloc。`inputs_lock.json` 绑定该
JSC 布局的文件内容及公开头目录。

探针从上游代码派生独立的默认 options 构造函数，完整 WebCore 的 `Document`
构造在 DOM 集成阶段接线。仅在目标组件的可重定位链接阶段选择测试可达函数，
正式链接保留正常 glibc CRT 入口。源文件许可证及三份上游 WebCore 通知随源锁登记。
台账副本只去除了许可证空白行的行尾空格，同时绑定原始成员和登记文本摘要。

```sh
python3 src/ports/webkit/tokenizer/build_probe.py --archive "$WPE_ARCHIVE" \
  --icu-archive "$XOS_ICU79_ARCHIVE" --sdk-build "$GLIBC_BUILD" \
  --sdk-profile "$GLIBC_CXX_PROFILE" --jsc-layout "$JSC_LAYOUT" --output "$TOKENIZER_OUT"
python3 tests/webkit_html_tokenizer_guest.py --target "$TOKENIZER_OUT" \
  --system "$SYSTEM" --output "$GUEST_OUT"
```

`JSC_LAYOUT` 指锁定 JSC 配置的 `layout/` 目录，包含 `cmakeconfig.h`、`lib/` 和
三个 `Headers` 目录。`SYSTEM` 从当前提交重建。客体从 FAT 读取实际 HTML 文件，核对
DOCTYPE、标签和属性大小写、属性转义、文本实体、EOF、缺失文件及资源恢复。
完整 HTML tree builder、DOM、样式、布局、Skia 画面及视口接入仍按页面计划逐段验收。
