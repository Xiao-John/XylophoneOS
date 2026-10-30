# CPython 静态 Pillow 核心

**仅单线程核心有受限资格；Pillow并发仍UNSUPPORTED/BLOCKED，保留真实dash allocator fault。**

本构建路径把固定 Pillow 11.3.0 的真实 `_imaging` 核心编入 CPython 3.14.9，
以 `PIL._imaging` 注册到 built-in 表，安装原始 `PIL` Python 包及许可证。
不是 `.so` 动态装载器，不增加 syscall、POSIX 兼容包装或第二套应用运行时。
实际已验范围和产物必须以[本轮报告](../reports/modern2_python_20261029/README.md)为准。

## 构建与来源

`src/ports/cpython/pillow/source_lock.json` 固定官方 PyPI 源包 SHA256、上游
`setup.py` 的核心 C 源清单及所有 C/头/Python 文件哈希。归档由调用者显式提供，
脚本不执行包的 setup.py、不自动下载或运行上游构建脚本。缓存输入再次校验。
Pillow 源文件不打补丁；生成的 XOS 配置头只设置版本和已经提供的真实 zlib。

```sh
COMPILER_PATH=/absolute/target-binutils-directory \
python3 scripts/build_cpython.py \
  --archive /absolute/Python-3.14.9.tar.xz \
  --sdk /absolute/xos-threaded-sdk \
  --build-python /absolute/matching-host-python \
  --zlib-prefix /absolute/verified-zlib-prefix \
  --pillow-archive /absolute/pillow-11.3.0.tar.gz --compile-probe
```

`--pillow-archive` 要求已有成功 zlib 回执。原有 SQLite/压缩选项可独立组合，
每种新组合都产生自己的指纹和资格，旧回执不能改绑。构建回执列出静态模块、
完整 SDK 输入、配置/命令、生成注册表和实际 ELF 哈希。

CPython `Modules/Setup` 只接受 C 标识符，因此使用 `_imaging` 生成编译规则与
`PyInit__imaging` 声明，并在原 config.c.in 模板中加入完整包名的 inittab 入口；
默认 `_imaging` 名也存在，包使用的是 `PIL._imaging`。生成配置头在 Pillow 源目录外。
构建器预建嵌套 object 目录，避免对第三方源文件作平台专用改写。

`stage_cpython.py --work WORK` 安装真实解释器、原始 `PIL` 的 `.py/.pyi` 文件和
原 LICENSE；stage manifest 逐文件计 SHA 并列明 Pillow 依赖和功能选择。
只做静态集成，不修改 Python 的文件身份、信号、进程或网络语义。

## 可复现实验

```sh
QEMU=/absolute/qemu-system-x86_64 \
python3 tests/pillow_static_guest.py \
  --work .cache/xos_seed/cpython/BUILD_FINGERPRINT \
  --image build/NEW-system/xos.img \
  --dash /absolute/verified-dash-ELF \
  --output build/NEW-guest
```

使用新目录和专用盘；测试器拒绝覆盖。xsh 与 dash 入口分别运行同一个原始
`PIL` 包和 C 扩展，比较已知 RGB 字节，做变换、PNG/BMP 文件往返、真实线程、
错误退出/恢复和进程资源回收。导出图像供独立宿主解码复核。
可选 `--extra-probe`、`--dependencies`、`--localpilot` 只用于实际依赖观察；
依赖失败不变成“应用通过”。含私有来源的工作盘/完整 traceback 仅保留在本地，
公开副本必须说明脱敏并绑定原始文件 SHA，不能称为无损串口副本。

## 明确边界

仅配置核心与 zlib；JPEG/JPEG2000/TIFF/WebP/AVIF、FreeType、LCMS、RAQM、
imagequant 和 Tk 等可选原生后端未集成。源码中其他纯 Python 插件存在不意味着
其格式或系统调用已验。`Image.show`、映射文件、屏幕捕获、完整字体/颜色管理和
所有 Pillow API 没有整体兼容资格；真实缺口继续报错。

保留 Pillow 默认图像尺寸炸弹防护。这里没有调整 UID/mode、O_NOFOLLOW、
符号链接或 LocalPilot 安全检查，也没有提供空 `_socket`、`select` 或 subprocess。
完整 Agent Core/API 1.0、身份、Operator 审批、UNKNOWN、HTTPS 和发行资格各自验收。
本接口只解除了原来“没有静态 `_imaging`”这一具体依赖阻塞。
