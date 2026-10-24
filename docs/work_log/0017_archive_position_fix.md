# 0017：S2 archive 链接与文件初始位置修复

2026-10-24；主 agent 负责本组。范围：仅修复报告已显现的问题并定向回归，
不重跑已完成的全量 gate，不扩展压力测试；后续压力测试由专人负责。
build/ 串行使用，未启动新子代理，未修改其他任务的代码。

## 定位与修改

`open_normalized` 将文件服务返回的文件大小错误记为当前偏移；服务普通打开从零
开始，只有 O_APPEND 从 EOF 开始。错误镜像值进入 SEEK_CUR，以及 newlib 的
ftell/fseek 缓冲定位。改为按 O_APPEND 设置 size 或 0；不改变文件服务和内核 ABI。

在 runtime_probe 新增独立 file-position 模式，检查已有 16 KiB 文件普通打开的
初始位置、dup 共享位置、相对 seek、stdio ftell、跨缓冲读/seek、SEEK_END 与 append。
新增 tests/archive_link_regression.py，只复制原 S2 现场盘，在副本导入探针和修复
Seed，使用保留的 archive/start.o/app.ld；不重做 as/ar/ranlib 或 S1/S3/S4。

修复前探针实际返回 initial-offset=16384 expected=0、退出1；证据
build/s2_position_before.log、build/s2_position_before_report.json。修复后位置探针退出0，
资源恢复 [130359,2,0]，原 archive、start.o、链接脚本哈希不变；证据
build/file_position_regression_report.json。原现场盘 SHA256 仍为
9cc1e1b988b1dedfe806ec52aee64ef3c9a4461034b64103622fe180b7f89868。

GNU 工具静态链接旧适配层，必须采用新 SDK 构建，不能只替换启动镜像。
## 最终证据与交接

状态：本组完成，无剩余文件占用。原34成员archive最终链接成功，产物与strip后产物
均在真实XOS退出42；5条客体命令，每条资源回到[130359,2,0]；输入哈希不变。
定向3项检查通过，不将旧压力报告改为全绿。无需重组archive或重跑已有全量测试。

执行命令：

```sh
make build
python3 tests/archive_link_regression.py --case-image build/e08_3_stress_last.img --position-only
python3 scripts/build_binutils.py \
  --sdk .cache/xos_seed/sdk_snapshots/SDK_HASH \
  --expected-sdk-manifest-sha256 SDK_HASH --jobs 10
python3 tests/archive_link_regression.py --case-image build/e08_3_stress_last.img \
  --seed-manifest SEED_MANIFEST
python3 -m py_compile tests/archive_link_regression.py
git diff --check
```

上面的SDK_HASH为 `f187691498b56720feb7ee118ad6cd70b2808cd4145ad7d4ea3d640ee51a1a93`，SEED_MANIFEST为
`.cache/xos_seed/binutils/build/a983a603cb4132f7ff02bc3471978e5099e28dad7a60f8a33658358938f14479/manifest.json`。构建日志build/s2_fix_build.log、s2_fix_seed_build.log；
定向报告build/archive_link_regression_report.json、file_position_regression_report.json，
串口build/archive_link_regression_serial.log，导出产物build/s2_fix_regression*.elf。
GNU源码/六补丁/配置未变，新SDK输入改变，脚本在新指纹目录重新构建9个静态工具；
本次客体验证只运行其中ld/strip，不把其余工具静态检查当作客体复验。

构建 `b1ded17e673ccffc`；源码SHA256 `b1ded17e673ccffce50418e0aca9fe8decbb577003749e6e5f7a5b2fc07d8ce1`。
xos.img SHA256 `baa37982b222a59a836def90c4586be70743ea88e26ac9b70843c8fa5f97507d`。
Seed manifest SHA256 `4986571a249ba23a814454848837eaebb0791dbb5dc6273c563df1c141dc4193`。
GNU/newlib/宿主交叉编译器版本与0015相同；本轮没有新增第三方依赖或许可变更。

- ld SHA256 `ca27d758ca2e1c750beaf80455f359370547a1359bf4e30af77c9c70a5822892`。
- strip SHA256 `76795c63b831e534b305eccdd9dd52e55007653b79724976147540f5510638d9`。
- 链接产物SHA256 `d460e6162b0089081b8414d48d4a0f0886a55871812817e9fed3b62fcf4e7e4f`。
- strip产物SHA256 `3ef1994fa038f5cabcf576acbed7f9ebc1b12e7c94510d089359b360fba08458`。

未运行make smoke、binutils_smoke、S0/S1/S3/S4、长soak、重启回归或重建一致性检查；
这些历史结果不重标到新版本。后续专人压力测试需使用本页新Seed与对应SDK，
不能沿用含旧静态运行时的47ddd307工具；保留原失败现场，测试脚本仅操作临时副本。
下一开发阶段仍E08-4；本修复不代表GCC/G++已实现，不增加压力测试任务。
localpilot/与日常工作盘未碰；未提交、推送或读取凭据。

