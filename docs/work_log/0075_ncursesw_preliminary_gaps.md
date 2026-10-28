# 0075：ncursesw 前期缺口处理

2026-10-28。用户要求开始处理前期缺口；W1 尚未完成。遵循先提交相关改动再验收，
本轮只做隔离构建和配置探针，没有运行客体验收或修改现有 SDK/发行材料。

## 产物与观察

- newlib agent 新增 `scripts/build_utf8_newlib.py`，校验 newlib 4.6.0.20260123 既有源码
  SHA256 `6ff27e3bf022666f43f7802255be680eeff722ac181b1725d21e2e8318604ee3`，在新目录
  分别构建 `--enable-newlib-mb` 的 single/threaded；threaded 保留 retargetable locking、
  `__DYNAMIC_REENT__` 及匹配现有线程 SDK 构建器的 profile receipt。构建器不覆盖 vendored
  库或 SDK；最终脚本 SHA256 `36cc6eb378c4efd4c5633706b20d729e923fc7999e286706f4b7c185681dc7d9`。
- 实际命令：`python3 scripts/build_utf8_newlib.py --archive .cache/xos_seed/threading_sources/newlib-4.6.0.20260123.tar.gz --output /tmp/xos_newlib_utf8_receipted_20261028 --jobs 8`。
  两种 profile 构建完成，输出头文件 `_MB_CAPABLE=1`；threaded 还启用 retargetable locking。
  single libc SHA256 `74c3494bda2e62e78998296cd54167c2e061873c4385574d66b3344c634c0f34`；
  threaded libc SHA256 `615c11d3247e0bb8931a48528147b288db6078055fff10e795a8f25464d2bc7e`。
  receipt 将状态记为 built_unverified；未验证 XOS 运行、locale、线程、SDK/ABI 或新产物的
  分发资格，也未宣称跨机器逐字节可复现。
- ncurses agent 新增 `scripts/probe_ncursesw.py`，锁定勘查输入 ncurses 6.5 上游 tarball
  SHA256 `136d91bc269a9a5785e5f9e980bc76ab57428f604ce3e5a5a90cebc767971cc6`，在必须
  新建的隔离目录针对显式 SDK 记录 configure/可选编译结果，不触碰 SDK。正式引入与逐成员
  许可审计未完成，探针源码锁不等于已选择发行版本。
- 实际命令：`python3 scripts/probe_ncursesw.py --archive /tmp/xos_ncurses_6_5_scout.tar.gz --sdk build/input_edit_final/sdk --output /tmp/xos_ncursesw_probe_final_20261028 --build`。
  configure 退出 0，但目标库编译退出 2：生成的 `term.h` 回退包含缺失的 `sgtty.h`；配置
  未检测到 `termios.h`、`sys/ioctl.h`。这份旧 SDK 是依赖探针输入，不是当前组合资格；
  日志和 report 留在该私有目录。configure 成功不能冒充 ncurses 移植成功。
- terminal agent 只读调查，主 agent 补充[终端契约草案](../contracts/terminal_w1.md)：
  通用设备/等待、前台可信委派、用户态终端策略、旧 ESC 兼容、服务多源等待和故障恢复
  分层；未分配 ABI，旧直通路径和 C26 例外仍需正式裁决及实现。

## 接续

W0 尚未完成目标 ncurses 调用路径冻结；W1 尚未实现或验收。下一步以候选 newlib 和当前
SDK 做隔离链接探针，核对 locale/宽度与线程 profile，定义真实终端公开类型/模式、通用
设备对象、IRQ4 队列及等待和迁移方案；涉及 ABI 先登记。原有 UTF-8 探针尚未在客体运行。
客体、权限、异常、资源/退出和组合回归统一在相关改动提交后执行；不把本次构建当验收。
