# `about`

- 控制台：实模式练习控制台（`make run_real_mode`）
- 语法：`about`
- 实现：`src/boot/x86/stage_two.asm`

## 行为

输出两行阶段说明：

```text
XylophoneOS: BIOS real_mode bring-up; x86_64 is next.
No protected memory or user tasks yet.
```

这是 0001 保留的 16 位练习镜像，不是默认 `xos.img` 的内核。

## 失败与边界

- 不接受参数。
- 不代表当前默认启动路径；默认内核走 `make run`。
- 没有保护模式、分页或用户态。

## 相关

- [help](help.md)、[halt](halt.md)
