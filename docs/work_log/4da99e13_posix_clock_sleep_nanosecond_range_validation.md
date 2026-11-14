<!-- coderabbit-ai-generated:v1 -->

# POSIX clock sleep nanosecond range validation

## 范围与实现

基线：`b44d1c773c2fc5ea2d2c46392264a46ed0fac94a`。
核实原实现对 tv_sec 直接进行无符号乘加，可能回绕或超出有符号时钟值范围。
`timespec_to_ns` 现在在乘加前以 `(INT64_MAX - tv_nsec) / 1000000000` 检查秒数，成功后才写出结果。
`clock_nanosleep` 在原有参数校验后统一调用，越界返回 EINVAL，覆盖单调绝对、实时绝对和相对睡眠及 nanosleep 包装器。
有效输入沿用原截止时间计算；不改变 ABI、时钟常量或系统调用。

## 验证

- `python3 tests/posix_clock_host.py`：通过。g++ 15.2.0，C++20，Wall/Wextra/Werror，UBSan；实际编译实现，以 stub 替代 XOS 系统调用和时钟头。
- 覆盖五种时钟、两种 flags、INT64_MAX、最大值减 1、最大值加 1、秒数越界、uint64 回绕大数、非法秒/纳秒、零与短请求、过期绝对请求、errno/rem 保持以及 nanosleep 错误映射。
- 将同一测试指向 git HEAD 原源码：在首个越界值的 EINVAL 断言失败，确认能检测原问题。
- 初次宿主编译因 glibc 声明的异常规格/nonnull 属性与 XOS 不同而失败；测试改用独立 time.h 声明后通过，产品代码未为宿主适配。
- `git diff --check`：通过。
- 客体测试未运行：缺少 x86_64-elf 交叉编译器及 build/ SDK、镜像、manifest。宿主 stub 验证不代表客体 ABI、启动或实际调度验证。

## 后续

具备目标工具链和构建产物后运行 `python3 tests/posix_clock_guest.py`。

## 已验证输入

- `src/user/libc/posix_clock.cpp`: SHA-256 `d9204393b9e7e2e6de94f98656be4aee9d440d64f49d9e352ad8a538e7eabb2d`
- `tests/posix_clock_host.py`: SHA-256 `fda2fd096a3c591b6095c1b1b43404a22a7b53deb8e18a688979b744c27042ad`
