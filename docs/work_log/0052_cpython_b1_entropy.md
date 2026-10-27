# 0052：CPython B1 系统安全熵

日期：2026-10-26

## 范围与选择

为已完成的 CPython PY3 A1–A3 补上真实系统熵，使 `getentropy()`、`os.urandom()`、
`random`、`secrets` 和依赖随机模块的 `statistics` 能运行。本组只覆盖公共随机字节
接口、x86-64 提供端、newlib 接线、QEMU CPU 配置及 CPython 客体验收；没有修改 dash、
xypm 源码、日常盘或正式 Release。

共享ABI新增syscall 63，避开线程sys38–52、Dash sys54–61和维护sys62。接口每次最多
请求256字节，目的缓冲区须为用户可写地址。x86-64检查CPUID.1:ECX[30]后才执行
RDRAND；每个64位字最多尝试10次并检查CF，完整请求先保存在内核256字节缓冲区，全部
成功后才复制到用户内存。硬件未支持返回`-38`，RDRAND有限尝试失败返回`-5`，坏用户
地址返回`-14`，超长/保留参数返回`-22`。不以时间戳、计时器、固定种子或伪随机代替。

newlib `getentropy()`最多256字节，映射上述结果为`ENOSYS`、`EIO`、`EFAULT`、`EINVAL`。
普通与线程 SDK 都包含该实现；删除线程库中旧的ENOSYS占位。QEMU默认CPU调整为
`qemu64,+rdrand`以覆盖正常VM启动；测试仍显式启动不带RDRAND的`qemu64`。默认启动器
没有传固定随机seed，也没有启用record/replay。

## 构建与客体证据

- 系统构建：`python3 scripts/build.py --output-dir build/cpython_py3_b1/system`
- build ID：`46cb97b1555633f1`；kernel.bin 385,084字节。
- 测试镜像：`build/cpython_py3_b1/system/xos.img`，SHA-256
  `93fef43692ba48b0d00625b1296b5c8c27716def8110e770e7f69c14ce78fd52`。
- 线程 SDK 命令：`python3 scripts/build_threading_sdk.py --newlib-prefix .cache/xos_seed/threading_newlib/prefix --output build/cpython_py3_b1/threading_sdk`。
  此次只需重建C运行库对象，故不要求本地缺失的GCC源码树；为本次C运行库
  更新复用当前SDK的C++归档（逐字节复制，未重建C++运行库）。其`libxos.a` SHA-256
  `737db38a0f608a62e8ae98e9be3bb179b85323207ff7cc0435be1f941876d5a0`，manifest SHA-256
  `3d00325f2b97094139588e042f91fcf05c077abef1db88226fbd3cb4d40699a9`。
- CPython 3.14.9使用新线程SDK与已锁定zlib 1.3.2构建，fingerprint
  `0739062ab231f71676c8`，`python.exe` SHA-256
  `c5edc4c65b466399520cb2e756495f340295a14375e5e8470e996ababe7063bf`。
- QEMU 11.1.2客体命令：
  `python3 tests/cpython_py3_b1_smoke.py --work .cache/xos_seed/cpython/0739062ab231f71676c8 --image build/cpython_py3_b1/system/xos.img --sdk build/cpython_py3_b1/threading_sdk`
- gate报告：`build/cpython_py3_b1_report.json`，SHA-256
  `6e29defc747c61724b2204afb31b6d58ae482e8f67eff13f8434e11410952b27`，状态passed。
- 带RDRAND guest验证256字节边界、0字节请求、坏地址errno、CPython多个`os.urandom`
  长度（包括512字节）、`random`、`secrets`和`statistics`；原生getentropy探针2项通过。
- 不带RDRAND guest原生探针确认`getentropy`返回`ENOSYS`；CPython `os.urandom`按当前
  配置报告`NotImplementedError`（无`/dev/urandom`回退设备）。两种guest运行后资源均
  回到`[130337,2,0]`。坏输入均以真实失败结束，不回退到固定内容。
- `python3 scripts/license_audit.py --build build/cpython_py3_b1/system`通过，7份许可
  材料完整；newlib归档逐成员许可证追溯仍未完成。

## 文件与边界

实现修改共享`process_abi.hpp`、x86-64 syscall路径、newlib适配、普通/线程QEMU启动配置
和线程SDK派生脚本；新增`tests/cpython_py3_b1_smoke.py`及两个小型客体探针。相关运行库、
ABI、QEMU行为及CPython PY3分档说明分别见`e06_libc.md`、`e04_loader_sdk.md`、
`cpython_py3_options.md`和`decisions.md`。

RDRAND可信度依赖CPU或hypervisor；恶意/故障hypervisor和QEMU固定seed/record-replay不在
保证范围。没有RDSEED、virtio-rng、熵池、多架构提供端或真实硬件验收。没有模拟RDRAND
连续清CF的故障注入，只验证代码中的10次有界失败路径。候选镜像留在独立build目录，
未替换共享build、日常工作盘或已发布镜像；本组未提交改动。

下一步可继续CPython PY3其他公共底座项目，或按朋友兴趣开始此前已分档的编辑器/用户态
工具移植；无需再为`statistics`阻塞单独补特判。
