# `alloc`

- 控制台：内核调试控制台（`make run`）
- 需要彩蛋：否
- 语法：`alloc`
- 实现：`src/kernel/core/console.cpp` 调用 `allocate_page`

## 行为

从 E820 可用页中分配一个 4 KiB 物理页，清零后返回物理地址。

成功：

```text
alloc result=ok phys=0x0000000000111000
```

失败（没有可分配页）：

```text
alloc result=out_of_memory
```

分配成功后，该页会记为“上一次分配”，供下一条 `free` 使用。

## 失败与边界

- 不检查虚拟映射；返回的是物理地址，没有对应虚拟地址语义。
- 连续执行 `alloc` 会覆盖“上一次分配”的记录，先前页不会被自动释放；
  当前没有通用的 `alloc <addr>`/按地址释放接口。调试时请成对使用 `alloc`/`free`。
- 分配的是零页；不代表内存内容已经过安全擦除或具备隔离保证。
- 没有堆分配器语义，不能用它替代 `new`/`delete`。

## 相关

- [free](free.md)、[mem](mem.md)
- 物理页保留范围见 `docs/architecture_and_boot.md`
