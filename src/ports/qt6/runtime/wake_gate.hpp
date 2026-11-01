// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/thread_core.hpp>

// Exactly one event-loop thread consumes and waits. Producers may call wake
// concurrently. A coalescing bit avoids counter wraparound: the owner clears it
// before checking work, and the kernel atomically compares zero before sleeping.
// The owner must exclude and join all wake callers before destroying this gate.
class xos_wake_gate {
    alignas(4) xos::u32 pending_ = 0;
public:
    xos_wake_gate() = default;
    xos_wake_gate(const xos_wake_gate&) = delete;
    xos_wake_gate& operator=(const xos_wake_gate&) = delete;
    bool take() { return __atomic_exchange_n(&pending_, 0u, __ATOMIC_ACQUIRE) != 0; }
    bool pending() const { return __atomic_load_n(&pending_, __ATOMIC_ACQUIRE) != 0; }
    xos::i64 wake() {
        __atomic_store_n(&pending_, 1u, __ATOMIC_RELEASE);
        return xos::thread::wake(&pending_, 1);
    }
    xos::i64 wait(xos::u64 deadline) { return xos::thread::wait(&pending_, 0, deadline); }
};
