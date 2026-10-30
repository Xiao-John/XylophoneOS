// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>
namespace xos::virtio_net {
// Private hardware/boot diagnostic API. Not a user syscall or socket interface.
void interrupt(u8 irq);
bool self_test(u32 profile);
}
