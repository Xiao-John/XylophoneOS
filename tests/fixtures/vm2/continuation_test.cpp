// SPDX-License-Identifier: Apache-2.0
#include "src/kernel/core/vm_continuation.hpp"
#include <cassert>
#include <cstdio>
using namespace xos;
static vm_step run(void*,vm_phase,u32,i64&) { return vm_step::again; }
int main() {
    vm_continuation work{}; int state=0;
    assert(!work.begin(0,1,&state,run)); assert(!work.begin(1,0,&state,run));
    assert(work.begin(1,9,&state,run) && work.active() && work.generation==9);
    assert(!work.begin(2,10,&state,run));work.cancel();
    assert(work.cancelled && work.phase==vm_phase::rolling_back);work.clear();
    assert(!work.active() && !work.cancelled && work.begin(2,10,&state,run));
    work.phase=vm_phase::publishing;work.cancel();
    assert(work.cancelled && work.phase==vm_phase::publishing);
    assert(vm_continuation_batch==32);std::puts("PASS VM continuation lifecycle");
}
