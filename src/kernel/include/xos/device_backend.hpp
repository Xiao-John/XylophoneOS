// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/device_abi.hpp>
namespace xos::device_grants {
struct resource { u64 physical, length; };
struct description { resource bars[6]; u32 configuration[64]; u8 irq; bool irq_available; };
}
namespace xos::platform {
i64 device_inspect(u64 instance, u64 rights, device_grants::description& out);
bool device_memory_enable(u64 instance);
bool device_dma_start(u64 instance);
bool device_dma_stop(u64 instance);
void device_disable(u64 instance);
bool device_irq_enable(u64 instance, u8 irq);
}
