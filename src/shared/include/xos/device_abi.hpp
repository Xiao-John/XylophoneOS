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
inline constexpr u64 device_right_all = 15;
inline constexpr u64 device_window_begin = 0x210000000000ull;
inline constexpr u64 device_mapping_slot_bytes = 0x1000000;
inline constexpr u32 device_mapping_slots = 16, device_max_grants = 16;
inline constexpr u64 device_window_end = device_window_begin + device_mapping_slots * device_mapping_slot_bytes;
inline constexpr u32 device_dma_max_pages = 1024, device_dma_owner_pages = 2048, device_dma_system_pages = 4096;
inline constexpr u64 device_memory_read = 1, device_memory_write = 2;
inline constexpr u64 device_attribute_mmio = 1, device_attribute_irq = 2,
    device_attribute_uncached = 4, device_attribute_configuration = 8;
inline constexpr u64 device_configuration_index = 0x100;
inline constexpr u64 device_deadline_infinite = ~u64{0};
enum class device_dma_direction : u64 { to_device = 1, from_device = 2, bidirectional = 3 };
// device_instance is 1 + PCI (bus << 8 | slot << 3 | function).
struct device_grant_input { u64 process_object, device_instance, rights, reserved; };
struct device_resource_input { u64 index, reserved; };
struct device_map_input { u64 index, offset, length, permissions; };
struct device_dma_input { u64 length, alignment; device_dma_direction direction; u64 reserved; };
struct device_irq_input { u64 sequence, reserved; };
struct device_output { u64 token, generation, rights, length, offset, attributes, address; };
struct device_request {
    u32 version, size;
    device_operation operation;
    u32 flags;
    u64 object_token, input_address;
    u32 input_length, output_length;
    u64 output_address, deadline_ns, reserved;
};
static_assert(sizeof(device_request)==64);
static_assert(sizeof(device_output)==56 && sizeof(device_grant_input)==32 && sizeof(device_map_input)==32);
static_assert(sizeof(device_dma_input)==32 && sizeof(device_resource_input)==16 && sizeof(device_irq_input)==16);
}
