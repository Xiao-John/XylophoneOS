// SPDX-License-Identifier: Apache-2.0
#include "core/cpu_accounting.hpp"
#include <cassert>
#include <cstdio>

int main() {
    using namespace xos;
    cpu_totals first{}, first_thread{}, other_thread{}, second{}, second_thread{};
    cpu_accounting usage;
    usage.valid = true;
    usage.last = 100;
    usage.select(&first, &first_thread, false, 100);
    usage.select(&first, &first_thread, true, 220); // syscall entry
    usage.charge(235);                           // nested kernel IRQ remains system
    usage.select(&first, &first_thread, false, 250);
    usage.select(&first, &first_thread, true, 300); // timer entry
    usage.stop(310);                              // scheduler and idle have no owner
    usage.stop(10000);
    usage.select(&second, &second_thread, true, 11000);
    usage.select(&second, &second_thread, false, 11025);
    usage.stop(11200);
    assert(first.user == 170 && first.system == 40);
    assert(first_thread.user == 170 && first_thread.system == 40);
    assert(second.user == 175 && second.system == 25);
    usage.select(&first, &other_thread, false, 12000);
    usage.select(&first, &other_thread, true, 12100);
    usage.stop(12110);
    assert(first.user == 270 && first.system == 50);
    assert(other_thread.user == 100 && other_thread.system == 10);
    assert(first_thread.user == 170 && first_thread.system == 40);
    first.include(second);
    assert(first.user == 445 && first.system == 75);
    usage.select(&second, &second_thread, false, 12200);
    usage.charge(12199);
    assert(!usage.valid && usage.process == nullptr && second.user == 175);
    assert(cpu_totals::add(~u64{0} - 5, 6) == ~u64{0});
    std::puts("PASS CPU user/system boundaries, nested IRQ, idle exclusion, process/thread totals, children and counter failure");
}
