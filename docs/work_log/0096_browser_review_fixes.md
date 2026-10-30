# Aurora Browser PR #19 审查修复

2026-10-29。以 PR #19 head `88cdbc01b0e30b2c2b449d9831d057468b9d6a77`
为起点，合并 main `3e5ccd0b5a5d7065ec89d7d9af7f7bb96ae137e2`；state 冲突保留
两侧事实。未修改原冻结 reports，也未把旧资格改绑到合并结果。

- HTTP 请求构造重新核对完整 host 分量，并使用校验后长度；增加分隔符、非法字符、
  大小写、253 字节有效 host 和无终止符的真实输入测试。此库仍是独立的无网络解析器。
- UI 在候选视图完成加载后替换旧视图；失败返回 false，保留页面、滚动、地址和历史；
  tab 切换失败恢复原 tab。旧视图延迟销毁，避免在其自身事件回调中直接删除。
- `tests/aurora_browser_acceptance.py --case negative` 加入外部 CSS 加载失败后的页面
  图像、历史、滚动和 tab 切换交互检查。候选与旧页面同时存在，瞬时峰值内存尚未测。

执行：`python3 tests/browser_http_test.py --output /tmp/xos-pr19-http-final`，宿主
clang ASan/UBSan，208 checks 和 4096 malformed vectors 通过；产物及编译器版本见该
目录 report.json。`python3 -m py_compile tests/aurora_browser_acceptance.py
 tests/browser_http_test.py` 与 `git diff --check` 通过。

未运行：修改后 Qt 目标编译、QEMU/真实客体交互、图形资源与峰值。宿主 pkg-config
不可用；未占用公共 build。下一步在私有输出目录用匹配的 SDK/Qt 重新构建浏览器及
合并主线系统，执行 negative、interactive、lifecycle 客体检查，绑定实际源码/ELF/
镜像，并单独确认并存视图的内存预算。提交不代表新组合客体资格。
