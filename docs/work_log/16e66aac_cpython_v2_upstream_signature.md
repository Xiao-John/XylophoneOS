# 16e66aac · glibc v2 冻结 CPython 源码的上游签名

从已验证的 v2 组件对应源码归档提取实际 `Python-3.14.9.tar.xz`。源码、
Python.org 的 Sigstore bundle 和 SPDX 2.3 文件分别匹配 XOS 源码锁。Sigstore
按 Python 3.14 发布人的公开身份与 OIDC 发布者核验源归档。完成官方 TUF
刷新，缓存 root 更新到版本 16；使用其可信根在禁止网络访问的进程中复跑通过。更改 OIDC 发布者
和输入摘要的两项对照都被拒绝。
[Python 发布页](https://www.python.org/downloads/release/python-3149/) ·
[Python 签名策略](https://www.python.org/downloads/metadata/sigstore/) ·
[源码与信任根回执](../reports/cpython_v2_source_signature_20261127/manifest.json)

受控环境使用 Sigstore 4.5.1。安装输入为上游精确提交的 requirements 文件，
启用 pip 的完整哈希检查并仅安装 wheel。命令使用与发行组件中对应源码同字节的
归档和 Python.org bundle。刷新后的可信根及 TUF 元数据摘要记录在回执。

```sh
python -m sigstore verify identity \
  --bundle Python-3.14.9.tar.xz.sigstore \
  --cert-identity hugo@python.org --cert-oidc-issuer https://github.com/login/oauth \
  Python-3.14.9.tar.xz
```

离线复跑先使用相同信任库状态，再追加 `--offline`。SPDX 文件本次单独核对
锁中的 SHA-256。冻结组件归档不改写。该回执证明这份已锁源归档的上游来历，
构建、静态替换和包的整包重现各按其回执验收。
