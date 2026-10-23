# `free`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：否
- 语法：`free`
- 实现：`src/kernel/core/console.cpp` 调用 `release_page`

## 行为

释放最近一次 `alloc` 成功返回的页：

```text
free result=ok
```

没有可释放页、或该页已经释放过：

```text
free result=invalid
```

## 失败与边界

- 不能指定地址；只释放“上一次分配”，不提供任意物理地址释放。
- `free` 不会解除任何虚拟映射。若该页仍被映射，调用者必须先 `unmap`；
  当前没有反向映射检查。
- 不回收页表页；`vmtest` 产生的中间页表会保留。
- double free 返回 `invalid`，不会误释放固件低端或内核页。

## 相关

- [alloc](alloc.md)、[mem](mem.md)、[vmtest](vmtest.md)
