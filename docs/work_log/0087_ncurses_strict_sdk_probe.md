# 0087：ncurses 6.5 与严格 UTF-8 SDK 探针

原记录中的机器临时目录已替换为 `${XOS_SCRATCH}` 路径模板；哈希和结果未改。

2026-10-29。作者镜像 HTTPS 连接失败后，从同一镜像的 HTTP 地址重新取得原包，
校验 SHA256 `136d91bc269a9a5785e5f9e980bc76ab57428f604ce3e5a5a90cebc767971cc6` 与
0075 锁定值完全一致，保存为忽略目录 `.cache/xos_seed/ncurses_sources/ncurses-6.5.tar.gz`。
HTTP 传输本身不提供来源认证，此处依靠已有锁定摘要校验内容；包不是唯一源码。

命令：`python3 scripts/probe_ncursesw.py --archive .cache/xos_seed/ncurses_sources/ncurses-6.5.tar.gz --sdk ${XOS_SCRATCH}/xos_w1_utf8_strict_sdk_20261029/sdk --output ${XOS_SCRATCH}/xos_ncurses_strict_probe_20261029 --build`。
配置退出 0、目标编译退出 2；`term.h` 包含 `sgtty.h` 失败。SDK libc SHA256 为
`75359f4594a01db330f3d7a1512ecb0ae60a6f94085f374ab459fa18787933bb`，探针输出中的
`USE_WIDEC_SUPPORT=1`、`HAVE_MBRTOWC=1` 和 `USE_SIGWINCH=1` 是配置结果，不能冒充
实际运行能力；目前终端类型、模式和信号语义仍缺失。宿主工具生成步骤不是目标能力。

当前没有最小 ncurses 目标可链接产物、客体验证、terminfo 交付或许可证完整审计；
W0 尚未冻结，W1/W2 仍未完成。按用户要求所有相关改动提交后才开展客体验收。
