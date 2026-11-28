# 9b82d2f0 · 共享 GCC 源码认证与 GNU keyring 更新

为 P0 glibc 共享运行库从 pre-release SDK 重建时，已锁 GCC 16.2.0 归档与
签名仍逐字节匹配，但当前官方 GNU keyring 的整体字节已更新。原构建器正确
拒绝了新 keyring。本模块保留拒绝事实，以既有签名身份审查新输入；不跳过
源码认证或改变运行时资格。

## 输入与实际签名

| 输入 | SHA-256 |
| --- | --- |
| GCC 16.2.0，107,200,820 bytes | `e6738e29597f733270731aa90600f37ffdc045079dfc27ec7e8192cc81085c3e` |
| 原上游签名 | `43d73202dcede15d31001c6ba0d28723014ef57e4dc815631772daadbe23bcd2` |
| 当前官方 GNU keyring，3,884,405 bytes | `0ed9052a6d6c70bf0cfcbdc59022f94c2493c6df02973f94d19e95ab9f125812` |
| 历史 keyring | `8013de59880f7a59f53b6bd207f4d2a408d67b84a82fa9cba1dbbf443428e2db` |

keyring 来源为 `https://ftp.gnu.org/gnu/gnu-keyring.gpg`，签名与源码 URL
分别记录在 [认证锁](../../src/ports/gcc/shared_source_auth.json) 和原源码锁。
在 Preview 2 的真实 `gpgv` 中校验原签名，退出 0；签名子钥仍为
`7F74F97C103468EE5D750B583AB00996FC26A641`，主钥仍为
`13975A70E63C361C73AE69EF6EEB81F8981C74C7`，均与原构建器已固定的身份一致。
本次输出未出现过期、撤销或失败状态，没有修改时钟或抑制错误。

新的版本化认证锁只接受上述当前 keyring 的确切字节，保留历史摘要供原版本
重放。`verify_gcc_shared_source.py` 核对两份源码锁的一致性，捕获有界、不可变
的归档、签名与 keyring 字节，使用私有副本执行 `gpgv`，复用 glibc 的严格
状态解析。验签后复核原输入与验证器；共享 GCC 构建从同一已验证归档快照
解包，避免验签和解包之间重新打开可变下载路径。最终 manifest 绑定完整
认证回执和摘要。

## 验收

使用 SDK Preview 2 Linux x86-64（归档 SHA-256
`60df6913fe2a56517e645c93673ebd9590ba3dd90acc56030c80c3738955cac9`）：

```sh
xos-sdk --workdir "$WORKSPACE" python3 "$SOURCE/tests/gcc_shared_source_auth.py" \
  --archive "$INPUTS/gcc-16.2.0.tar.xz" \
  --signature "$INPUTS/gcc-16.2.0.tar.xz.sig" \
  --keyring "$INPUTS/gnu-keyring.gpg" --output "$NEW_REPORT"
```

17 项通过：真实上游签名与当前 keyring、实际篡改签名/keyring 文件的拒绝、
解包字节替换拒绝，以及错误主钥/子钥、重复签名、非零验证器退出、过期/撤销/
失败状态的定向状态夹具。状态夹具只测试解析策略，不冒充产生了真实撤销的
上游密钥。另用前一提交的原构建器重放同组输入，实际观察原 keyring 哈希拒绝；
原始日志摘要与路径模板化导出均保留。

[实际回执、正负例与原始 GPG 状态](../reports/gcc_shared_source_auth_20261127/manifest.json)

本模块只完成来源认证维护。新 shared GCC 的交叉构建和目标内 C++/线程/异常
验收另行记录，公开动态身份、激活与 D4 应用组合未因签名通过而取得资格。
