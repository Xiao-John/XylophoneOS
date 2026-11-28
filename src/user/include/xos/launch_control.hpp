// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/launch_control_abi.h>
#include <xos/process_abi.hpp>

namespace xos::launch {
using descriptor = xos_launch_descriptor;
using artifact = xos_launch_artifact;
using message = xos_launch_message;
struct diagnostic {
    i64 status;
    u32 phase;
    u64 generation;
    artifact admitted;
};
// Must be bounded, non-reentrant, and outlive the child registration. A null
// callback permits only an all-zero artifact; an identity is not authority.
using admission_check = i64 (*)(void* context, u64 child, const artifact& current,
                                const artifact& requested, u64 absolute_deadline);
// Only explicit terminal + launch-control composition selects the six-channel
// mode. Ordinary registrations retain the legacy four-channel owner limit.
i64 record_child(u64 child, u64 absolute_deadline, descriptor& output,
                 const artifact& initial = {}, admission_check check = nullptr,
                 void* context = nullptr, bool extended_channels = false);
i64 await_ready(u64 child, diagnostic& output);
i64 close_control(u64 child);
i64 last_diagnostic(u64 child, diagnostic& output);
i64 poll();
i64 wait(u64 child, process_status& output, u32 flags = 0);
i64 notify_ready(const descriptor& control, i64 status = 0, u32 phase = 0);
i64 notify_ready(const descriptor& control, const artifact& admitted,
                 i64 status = 0, u32 phase = 0);
i64 prepare_exec(const descriptor& active, u64 absolute_deadline, descriptor& pending);
i64 prepare_exec(const descriptor& active, u64 absolute_deadline,
                 const artifact& requested, descriptor& pending);
i64 cancel_exec(const descriptor& pending);
i64 cancel_exec(const descriptor& pending, const artifact& admitted);
}
