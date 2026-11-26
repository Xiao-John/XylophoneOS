# ClarkE 的原生 HTTPS 传输接口

将 ClarkE 的 HTTPS 取件逻辑移入 `browser_http`，供当前浏览器和后续 WebKit 网络任务
共用。路由调用者提供可信 net2 服务、预期 IPv4 地址及 DER 信任根。原安装入口仍按
自己的 origin 配置选择路由。TLS 名称、SNI 和 HTTP Host 继续使用 URL 主机名，
DNS 模式要求 net2 返回预期地址。HTTP 和 HTTPS 的成功回执在同一份经过检查的原始
字节中分别记录头字段及正文范围。

从 `3f11e613` 重建 ClarkE 和真实 Mbed TLS，打包并离线安装到 FAT。隔离 Linux ARM64
中的 QEMU 11.1.3 从安装路径启动浏览器。DNS 探针系统 `42cb6714fdf39ede` 的六项检查
通过，覆盖 HTML、同源
CSS、BMP 与实际渲染像素、明文样式拒绝、错误 SAN 和未知 CA 拒绝、DNS 路由变化拒绝、
双向 TLS 关闭和资源回收。服务端记录四个完成 HTTP 请求、六次 SNI 和四次正常 TLS
关闭。测试使用现有 Qt/liteHTML 安装入口和受控 CA。

宿主 HTTP 检查通过 212 项，并执行 4096 组字节向量。Net2 客户端及严格无 libc 链接在
Linux x86-64 通过。macOS ARM64 的宿主尝试完成 C++ 客户端运行后，在编译 x86-64
汇编入口时终止。客体首次预检拒绝输出到其规定工作区之外，修正容器中的挂载位置后
使用相同镜像和 XPK 完成正式回放。

WebKit 的真实 NetworkDataTask 接线、公共信任根和 HTTP 流式能力仍按 M3 验收。
[传输接口](../../src/ports/browser_http/README.md) ·
[构建与客体回执](../reports/clarke_native_https_transport_20261127/manifest.json)
