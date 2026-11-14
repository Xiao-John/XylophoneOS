<!-- coderabbit-ai-generated:v1 -->

# Threaded clock error returns

基线：`bfcc09af556d6c6760cc8ebe70c03b55ffaf1234`。逐条核实用户提供的三条 review 数据，均仍成立。

## 实现和兼容

- `clock_settime` 继续拒绝设置时间，改为 errno=EPERM、返回 -1；修复调用方的错误检测。
- `clock_nanosleep` 在分支前验证 CLOCK_REALTIME/CLOCK_MONOTONIC；无效 ID 返回 EINVAL，绝对请求继续返回 ENOTSUP，有效相对请求继续委托 nanosleep。CPU 计时时钟及 RAW/COARSE 别名不作为此线程睡眠接口支持的时钟；普通 libc 的独立实现不在本次范围。
- 委托成功返回 0，失败返回 errno 中的正数错误码；req/rem 原样传递。
- 无 syscall、布局或常量更改，无新增 newlib 私有依赖。兼容影响限于用户要求的错误检测修复；回退可还原本次 wrappers 修改。

## 验证

- `python3 tests/threading_clock_host.py` 通过（exit 0）：g++ 15.2.0、Python 3.14.4、C++20、Wall/Wextra/Werror、UBSan。从实际 pthread.cpp 提取两个完整 wrapper 编译，使用确定性 nanosleep stub；覆盖 EPERM、非法时钟两种 flags、参数校验、有效时钟、ENOTSUP、成功及 EINTR/EINVAL/EIO 转换、req/rem 与空 rem。
- `git diff --check` 通过（exit 0）。
- 额外将测试指向 HEAD 原文件的临时副本：原代码在 Werror 下因 clock_id 未使用而编译失败，未到达运行断言；不记为行为回归证明。
- 客体 threading smoke 未运行：缺少 x86_64-elf-g++ 和 build/threading_sdk/manifest.json、SDK/镜像。宿主 wrapper 测试不证明真实客体调度或 ABI。
- 后续：在准备好工具链及线程 SDK 后运行 `python3 tests/threading_pthread_smoke.py`。

## 输入标识

- `src/user/threading/pthread.cpp`: `32aa91e74926594e98f7b9910f6885d271c5a7ae572b511da71f41b12b0bba78`
- `tests/threading_clock_host.py`: `5927252c7fe0ae2c04a9c342833ac45933b5fa731f1d83c864e662853ecef6de`
