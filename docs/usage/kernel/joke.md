# `joke`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：**是**
- 语法：`joke`
- 实现：`src/kernel/core/console.cpp`

## 行为

按固定次序输出一条冷笑话，重复调用会循环五条：

1. `Why did the page fault cross the road? It had a valid CR2.`
2. `Two hard things in OSDev: naming things, cache invalidation, and off-by-one errors.`
3. `Guo YePeng asked for one tiny feature. The roadmap gained an E-number.`
4. `64-bit kernel, 8-bit jokes. The jokes are not paged in.`
5. `This kernel enforces W^X. The jokes are write-only.`

输出带 `[joke] ` 前缀。索引在每次调用后递增，重启 QEMU 会复位。

## 失败与边界

- 使用固定数组与调用计数，不使用随机数、时间或额外状态；重复运行结果一致。
- 不引入延迟、分配或错误注入。
- 彩蛋关闭时命令不存在。

## 相关

- [guo](guo.md)、[about](about.md)
