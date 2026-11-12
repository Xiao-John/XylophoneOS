// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>

namespace xos {
struct cpu_totals {
    u64 user = 0;
    u64 system = 0;

    static u64 add(u64 left, u64 right) { return right > ~u64{0} - left ? ~u64{0} : left + right; }
    void include(const cpu_totals& other) {
        user = add(user, other.user);
        system = add(system, other.system);
    }
};

// One execution owner on the current single CPU. Stopping before idle and
// choosing one mode at each boundary prevents charging elapsed sleep twice.
struct cpu_accounting {
    cpu_totals* process = nullptr;
    cpu_totals* thread = nullptr;
    u64 last = 0;
    bool system = true;
    bool valid = false;

    void charge(u64 now) {
        if (!valid) { return; }
        if (now < last) { valid = false; process = nullptr; thread = nullptr; return; }
        const u64 elapsed = now - last;
        if (process != nullptr) {
            u64& total = system ? process->system : process->user;
            total = cpu_totals::add(total, elapsed);
            u64& thread_total = system ? thread->system : thread->user;
            thread_total = cpu_totals::add(thread_total, elapsed);
        }
        last = now;
    }

    void select(cpu_totals* next, cpu_totals* next_thread, bool kernel, u64 now) {
        charge(now);
        if (!valid) { return; }
        process = next;
        thread = next_thread;
        system = kernel;
    }

    void stop(u64 now) { select(nullptr, nullptr, true, now); }
};
}
