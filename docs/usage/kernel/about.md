# `about`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：**是**
- 语法：`about`
- 实现：`src/kernel/core/console.cpp`

## 行为

输出阶段、架构、实现语言、真实构建 ID 与致谢：

```text
XOS E04 | x86-64 | NASM + restricted C++ | build=<本次构建 ID>
Not Linux, not trying to be. Guo YePeng is in the credits; the bugs are still mine.
```

构建 ID 来自本次镜像的源码摘要，不是编译时间或随机值。

## 失败与边界

- 彩蛋关闭时命令不存在。
- 只显示文本，不执行版本检查、联网或更新。
- `E04` 表示当前实现阶段，不代表 0.0-boot 或 O01–O22 全部通过。

## 相关

- [guo](guo.md)、[joke](joke.md)、[索引](../index.md)
