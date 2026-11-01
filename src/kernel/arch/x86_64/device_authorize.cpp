// SPDX-License-Identifier: Apache-2.0
// sys_device dispatch (contracts/device_authorization_v1.md), segment 1a:
// request snapshot and frozen header validation. Known operations are not yet
// implemented and honestly return device_unknown; segments 1b-1e replace that
// with the real grant/map/irq/dma machinery one PR at a time.
#include <xos/device_abi.hpp>
#include "frame.hpp"
namespace xos {
bool user_range_ok(u64 address, u64 length, bool write);
void copy_from_user(void* destination, u64 source, u64 length);
void* device_authorize_syscall(interrupt_frame* frame);

void* device_authorize_syscall(interrupt_frame* frame) {
    i64 result = device_unknown;
    const u64 request_address = frame->rdi;
    do {
        if (frame->rsi != 0 || frame->rdx != 0) { result = device_invalid; break; }
        device_request request{};
        if (!user_range_ok(request_address, sizeof(request), false)) { result = device_fault; break; }
        copy_from_user(&request, request_address, sizeof(request));
        const u32 operation = static_cast<u32>(request.operation);
        if (request.version != 1 || request.size != sizeof(request) || request.reserved != 0 ||
            request.flags != 0 || operation < 1 || operation > 11) { result = device_invalid; break; }
        if (request.deadline_ns != 0 && request.operation != device_operation::irq_wait) {
            result = device_invalid; break;
        }
        if (request.input_length != 0 &&
            (request.input_address == 0 || !user_range_ok(request.input_address, request.input_length, false))) {
            result = device_fault; break;
        }
        if (request.output_length != 0 &&
            (request.output_address == 0 || !user_range_ok(request.output_address, request.output_length, true))) {
            result = device_fault; break;
        }
        // Segment 1a: the frozen operation set exists; no operation carries
        // machinery yet. unknown marks the transient state and must disappear
        // from the probes when 1b lands the grant table.
        result = device_unknown;
    } while (false);
    frame->rax = static_cast<u64>(result);
    return frame;
}
}
