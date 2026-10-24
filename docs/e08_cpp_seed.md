# E08-5：静态C++工具链

0022已通过六项ABI、原生G++4组/14命令及C++编辑重启增量；综合结论见
reports/e08_acceptance.md。版本与限制以state.md、work_log/0022_cpp_seed_acceptance.md为准。交叉构建的ABI
探针、原生g++/cc1plus设施gate、E08-6编辑持久化分别报告，不互相替代。
默认静态/local-exec，异常、RTTI、TLS、string/vector为必需；iostream非本轮必需。

## 输入与派生

原A/B清单src/ports/gcc/e08_5_target_runtime_manifest.json、e08_5_gxx_manifest.json
保留。A库对象用SDK v4，原B工具静态host闭包不含异常/RTTI；A目标库启用这些设施。
应用链接采用SDK v5：
.cache/xos_seed/sdk_snapshots/3a302b5cd7e1cdab0f594b0d16d7ca92b753fec7b2efcc6347b01e5a69542edd，
manifest SHA256同目录名。对象构建SDK与新应用链接SDK分开绑定，旧产物不重标来源。

原库包含旧libc探测配置下的GNU TLS回退，与v5重复定义。接收脚本派生库，采用
GNU现有“libc提供TLS退出入口”配置并删除无须链接的回退成员，原库不改动：

```sh
python3 scripts/derive_cpp_runtime.py \
  --manifest src/ports/gcc/e08_5_target_runtime_manifest.json \
  --frontend-manifest src/ports/gcc/e08_5_gxx_manifest.json \
  --prefix .cache/xos_seed/gcc/e08_5/target_runtime/prefix \
  --sdk .cache/xos_seed/sdk_snapshots/3a302b5cd7e1cdab0f594b0d16d7ca92b753fec7b2efcc6347b01e5a69542edd \
  --output-root .cache/xos_seed/gcc/relinks/target_runtime_v5_receipt
```

输出目录必须不存在；已有该派生时直接核对manifest/输入hash，不覆盖它来重跑。
原g++也有已显现lrealpath漏返回值，仅重链接g++/cc1plus：

```sh
python3 scripts/relink_gcc_seed.py --gxx \
  --source-manifest src/ports/gcc/e08_5_gxx_manifest.json \
  --work .cache/xos_seed/gcc/e08_5/gxx \
  --sdk .cache/xos_seed/sdk_snapshots/3a302b5cd7e1cdab0f594b0d16d7ca92b753fec7b2efcc6347b01e5a69542edd \
  --output-root .cache/xos_seed/gcc/relinks/gxx_lrealpath_v5
```

保留实际链接日志/输入对象hash，无configure/all-gcc重编；collect2不验收，profile
显式使用真正GNU ld。GCC16.2工具/标准库保留GNU条款及运行库例外，新XOS脚本Apache-2.0。

## 安装与客体调用

```sh
python3 scripts/prepare_gcc_seed.py \
  --gcc-manifest .cache/xos_seed/gcc/relinks/open_capacity_fix/seed_manifest.json \
  --binutils-manifest .cache/xos_seed/binutils/build/a983a603cb4132f7ff02bc3471978e5099e28dad7a60f8a33658358938f14479/manifest.json \
  --gxx-manifest .cache/xos_seed/gcc/relinks/gxx_lrealpath_v5/seed_manifest.json \
  --runtime-manifest .cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/manifest.json \
  --runtime-prefix .cache/xos_seed/gcc/relinks/target_runtime_v5_receipt \
  --target-sdk .cache/xos_seed/sdk_snapshots/3a302b5cd7e1cdab0f594b0d16d7ca92b753fec7b2efcc6347b01e5a69542edd \
  --output-root build/cpp_bundle
```

只生成明确白名单，不自动写日常盘。guest C++头位于/sysroot/cxx_include/<index>，
-isystem先于C头的-idirafter，支持#include_next。目标库在/sysroot/lib，固定/sysroot
profile不宣称任意位置重定位。普通C工具与其原SDK静态绑定来源单独保留。

导入后sup>示例：

```text
exec-driver /usr/bin/x86_64-elf-g++ -std=gnu++17 -static --sysroot=/sysroot -c /src/main.cpp -o /out/main.o
exec-driver /usr/bin/x86_64-elf-g++ -static --sysroot=/sysroot /out/main.o -o /out/app.elf
exec-file /out/app.elf
```

原生设施gate为tests/cpp_seed_smoke.py，参数同gcc_seed_smoke.py；E08-6 C++增量为
`tests/e08_integration_smoke.py --language cpp`，传明确CPP白名单/根并显式--run-guest。
测试均创建专用临时盘，离线导出只在QEMU关闭后；不重复旧C/压力轮次。
无线程/动态链接/动态TLS/DTV/DSO卸载，不宣称完整标准库、C++23 modules、插件、
任意流水线或工具链自举。异常/RTTI/TLS不能为赶进度静默关闭。
