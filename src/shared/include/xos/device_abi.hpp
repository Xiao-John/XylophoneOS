// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>
namespace xos {
// device_authorization_v1（contracts/device_authorization_v1.md）冻结面。
inline constexpr u64 sys_device = 112;
inline constexpr i64 device_ok=0, device_invalid=-1, device_fault=-2, device_denied=-3,
    device_stale=-4, device_busy=-5, device_resources=-6, device_no_device=-7,
    device_timeout=-8, device_closed=-9, device_io=-10, device_unknown=-11;
enum class device_operation : u32 { grant=1, query=2, map=3, unmap=4, dma_alloc=5,
    dma_release=6, irq_bind=7, irq_wait=8, irq_ack=9, revoke=10, close=11 };
inline constexpr u64 device_right_query=1ull<<0, device_right_mmio=1ull<<1,
    device_right_dma=1ull<<2, device_right_irq=1ull<<3;
struct device_request {
    u32 version, size;
    device_operation operation;
    u32 flags;
    u64 object_token, input_address;
    u32 input_length, output_length;
    u64 output_address, deadline_ns, reserved;
};
static_assert(sizeof(device_request)==64);
}
