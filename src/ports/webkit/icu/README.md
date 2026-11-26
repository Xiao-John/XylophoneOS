# ClarkE 的 ICU4C 静态依赖

使用 ICU4C 79.1 的 `data`、`i18n` 和 `uc` 组件。构建器先用 Unicode 官方仓库
固定版本的公钥表核对归档签名，再分开构建 Linux 宿主数据工具和 XOS 静态归档。
ICU 在构建系统中识别 `x86_64-unknown-xos`，目标关闭共享库、插件动态装入和文件
`mmap`。Unicode 数据打入目标静态归档。[源码锁](source_lock.json)

需要 Linux 的 C/C++ 编译器、GNU make 4、Bash、Python 3.12 或更新版本和 `gpgv`。
使用与 glibc C/C++ SDK 上游构建回执匹配的交叉编译器与 binutils。取得源码归档、
对应 `.asc` 和固定 Git 提交下的原始 `KEYS` 文件后运行。

```sh
python3 src/ports/webkit/icu/build_target.py \
  --archive "$ICU_ARCHIVE" --signature "$ICU_ASC" --keys "$ICU_KEYS" \
  --sdk-build "$GLIBC_BUILD" --sdk-profile "$GLIBC_CXX_PROFILE" \
  --output "$ICU_BUILD_DIR" --jobs 4
```

`install` 子目录提供头文件和目标库，根目录 `manifest.json` 绑定源码、SDK 树、
构建脚本、交叉工具与三个归档。WebKit 配置时，将该安装目录和目标 sysroot 放入
目标查找根，继续保持宿主库隔离。

客体夹具 [icu_smoke.c](../../../../tests/fixtures/webkit/icu_smoke.c) 通过三个目标归档
静态链接，验证 NFC 标准化、德语大小写、英文词边界和排序。合格标记为
`ICU_SMOKE_OK`，需要同时核对真实进程退出及资源恢复。JSC 解释器和 WebCore 的
运行各自验收。

```sh
export XOS_ICU_SDK="$GLIBC_BUILD/sysroot"
export XOS_ICU_CXX_INCLUDES="$ICU_BUILD_DIR/drivers/cxx-includes.txt"
export XOS_ICU_CC="$(command -v x86_64-elf-gcc)"
export XOS_ICU_CXX="$(command -v x86_64-elf-g++)"
"$ICU_BUILD_DIR/drivers/cc" -c -I "$ICU_BUILD_DIR/install/include" \
  tests/fixtures/webkit/icu_smoke.c -o "$ICU_BUILD_DIR/icu-smoke.o"
"$ICU_BUILD_DIR/drivers/cxx" "$ICU_BUILD_DIR/icu-smoke.o" -Wl,--start-group \
  -L"$ICU_BUILD_DIR/install/lib" -licui18n -licuuc -licudata -Wl,--end-group \
  -o "$ICU_BUILD_DIR/icu-smoke.elf"
python3 tests/qt6_sdk_probe.py --image "$XOS_INSTALL_ISO" \
  --payload "$ICU_BUILD_DIR/icu-smoke.elf" --report "$ICU_BUILD_DIR/guest.json" \
  --marker ICU_SMOKE_OK
```
