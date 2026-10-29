// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/display_abi.hpp>
namespace xos::virtio_gpu {
bool init();
bool available();
display_mode mode();
void write(u64 offset,const u8* data,u64 size);
bool present(display_rect rect);
bool resource_limit_test();
bool self_test(); // serial boot monitor only, before the scheduler/clients start
}
