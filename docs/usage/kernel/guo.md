# `guo`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：**是**（`easter_eggs: true`）
- 语法：`guo`
- 实现：`src/kernel/core/console.cpp`

## 行为

输出 Guo YePeng 的仪式性问候：

```text
[guo] name="Guo YePeng" role="friend, chaos consultant"
[guo] status=did_not_panic_yet ego=+1
[guo] tip=if it breaks, check the GDT first
```

纯文本输出，不改变任何内存、权限、异常或调度行为。

## 失败与边界

- 彩蛋关闭时命令不存在，输入 `guo` 返回 `ERROR: unknown_command`。
- 不接受参数；不对应任何真实用户、账户或权限。
- 不是稳定 ABI；后续终端迁往用户态时可整体搬走或删除。

## 相关

- [joke](joke.md)、[about](about.md)、[索引](../index.md)
