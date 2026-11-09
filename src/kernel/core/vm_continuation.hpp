// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>
namespace xos {
// Each step is called with at most this many units of page work. Persistent
// state belongs to the caller's bounded transaction object, never its stack.
inline constexpr u32 vm_continuation_batch = 32;
enum class vm_phase : u8 { idle, preparing, publishing, rolling_back };
enum class vm_step : u8 { again, prepared, finished, failed };
using vm_step_function = vm_step (*)(void*, vm_phase, u32, i64&);
struct vm_continuation {
    u64 owner_tid = 0;
    u64 generation = 0;
    vm_phase phase = vm_phase::idle;
    bool cancelled = false;
    i64 failure = 0;
    void* context = nullptr;
    vm_step_function step = nullptr;
    bool active() const { return phase != vm_phase::idle; }
    bool begin(u64 tid, u64 transaction_generation, void* state, vm_step_function function) {
        if (active() || !tid || !transaction_generation || !state || !function) return false;
        owner_tid=tid; generation=transaction_generation; phase=vm_phase::preparing;
        cancelled=false; failure=0; context=state; step=function; return true;
    }
    void cancel() {
        if (!active()) return;
        cancelled=true;
        if (phase==vm_phase::preparing) phase=vm_phase::rolling_back;
    }
    void clear() { *this = vm_continuation{}; }
};
}
