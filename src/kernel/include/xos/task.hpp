#pragma once
#include <xos/types.hpp>

namespace xos {
struct task_snapshot {
    u32 pid;
    u64 ticks;
    const char* name;
};

bool tasks_init();
[[noreturn]] void tasks_start();
u32 task_count();
task_snapshot task_at(u32 index);
}

namespace xos::arch {
void set_kernel_stack(u64 top);
}
