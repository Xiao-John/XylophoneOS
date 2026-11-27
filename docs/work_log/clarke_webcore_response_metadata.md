# ClarkE 的原生响应元数据

软件 WebCore 使用已接入的目标 OpenSSL 解析叶证书的完整 DER，向检查器提供主题、UTC
有效期和 DNS、IPv4、IPv6 备选名称。叶证书和其验证状态仍来自传输端；检查器读取的
摘要属于展示数据。空链、截断 DER 和含尾随数据的 DER 单独验证。样例证书的两个
时间和四个备选名称在真正的目标应用中逐项核对。

认证挑战借用 WebCore 上游的保护空间、凭据、响应和错误类型。回调保存弱引用，两个
不同的活跃回调归属不同挑战。客体核对同一挑战的复制、不同回调的区分、继续请求
的分派和回调拥有者销毁后的引用失效。HTTP 挑战须由原生传输交付，凭据存储、提示
与响应重试各有独立验收门。

锁定源码重放后，先复验检查器、加载器和视频帧的实际统一编译单元，再从同一编译图
构建辅助对象。编译中发现通用响应的文件名钩子拼写与调用方不一致，修复后重编
响应对象。两个探针使用同一普通镜像 `1958db24f4ad591d` 和独立 FAT 盘，经 xsh
启动退出 0，资源回到 `129709 / 3 / 1`。最终锁定源码重编得到字节相同的两个 ELF。静态链接仍
会报告现有 glibc 的 `signal`、`sleep`、`sysconf` 等未实现入口。完整 WebCore 和
整页显示按各自门验收。

```sh
python3 tests/qt6_sdk_probe.py --image "$SYSTEM_ISO" --payload "$CERTIFICATE_ELF" \
  --marker 'XOS_WEBKIT_CERTIFICATE_OK subject validity dns ipv4 ipv6 invalid_der' \
  --report "$CERTIFICATE_GUEST_REPORT"
python3 tests/qt6_sdk_probe.py --image "$SYSTEM_ISO" --payload "$CHALLENGE_ELF" \
  --marker 'XOS_WEBKIT_CHALLENGE_OK bound_callback comparison expiration' \
  --report "$CHALLENGE_GUEST_REPORT"
```

[目标编译与独立客体](../reports/clarke_webcore_response_metadata_20261127/manifest.json)
