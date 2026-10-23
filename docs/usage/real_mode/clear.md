# `clear`

- 控制台：实模式练习控制台（`make run_real_mode`）
- 语法：`clear`
- 实现：`src/boot/x86/stage_two.asm`

## 行为

1. 调用 BIOS 文本模式 3，重设 80×25 VGA 文本屏；
2. 只向串口发送 ANSI 清屏/定位序列 `ESC[2J ESC[H`；
3. 输出 `Screen cleared.` 并重新显示提示符。

## 失败与边界

- 清屏后的 VGA 像素没有单独自动验收。
- ANSI 序列只对支持的串口终端有效；BIOS 屏不依赖 ANSI。
- 不清理滚动历史或宿主终端缓冲区。

## 相关

- [help](help.md)
