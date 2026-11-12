// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/device_abi.hpp>
#include <xos/sdk.hpp>

namespace xos::device {
inline i64 invoke(device_operation operation, u64 token, const void* input, u32 input_size,
                  device_output* output = nullptr, u64 deadline = 0) {
    device_request request{};
    request.version = 1; request.size = sizeof(request); request.operation = operation;
    request.object_token = token; request.input_address = reinterpret_cast<u64>(input);
    request.input_length = input_size; request.deadline_ns = deadline;
    if (output) { *output = {}; request.output_address = reinterpret_cast<u64>(output); request.output_length = sizeof(*output); }
    const i64 result = sdk::syscall(sys_device, reinterpret_cast<u64>(&request), 0, 0);
    if (result && output) *output = {};
    return result;
}
inline i64 grant(u64 process_object, u64 instance, u64 rights, device_output& out) {
    const device_grant_input input{process_object, instance, rights, 0};
    return invoke(device_operation::grant, 0, &input, sizeof(input), &out);
}
inline i64 query(u64 token, u64 index, device_output& out) {
    const device_resource_input input{index, 0};
    return invoke(device_operation::query, token, &input, sizeof(input), &out);
}
inline i64 configuration(u64 token, u32 offset, u32& value) {
    value = 0;
    if ((offset & 3) || offset > 252) return device_invalid;
    device_output out{};
    const i64 result = query(token, device_configuration_index + offset / 4, out);
    if (!result) value = static_cast<u32>(out.attributes >> 32);
    return result;
}
inline i64 map(u64 token, u64 index, u64 offset, u64 length, u64 permissions, device_output& out) {
    const device_map_input input{index, offset, length, permissions};
    return invoke(device_operation::map, token, &input, sizeof(input), &out);
}
inline i64 unmap(u64 token) { return invoke(device_operation::unmap, token, nullptr, 0); }
inline i64 dma_allocate(u64 token, u64 length, u64 alignment, device_dma_direction direction, device_output& out) {
    const device_dma_input input{length, alignment, direction, 0};
    return invoke(device_operation::dma_alloc, token, &input, sizeof(input), &out);
}
inline i64 dma_release(u64 token) { return invoke(device_operation::dma_release, token, nullptr, 0); }
inline i64 irq_bind(u64 token, device_output& out) {
    const device_resource_input input{6, 0};
    return invoke(device_operation::irq_bind, token, &input, sizeof(input), &out);
}
inline i64 irq_wait(u64 event, u64 acknowledged, u64 deadline, device_output& out) {
    const device_irq_input input{acknowledged, 0};
    return invoke(device_operation::irq_wait, event, &input, sizeof(input), &out, deadline);
}
inline i64 irq_ack(u64 event, u64 sequence) {
    const device_irq_input input{sequence, 0};
    return invoke(device_operation::irq_ack, event, &input, sizeof(input));
}
inline i64 revoke(u64 token) { return invoke(device_operation::revoke, token, nullptr, 0); }
inline i64 close(u64 token) { return invoke(device_operation::close, token, nullptr, 0); }
}
