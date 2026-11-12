// SPDX-License-Identifier: Apache-2.0
#include "src/kernel/core/cow_snapshot.hpp"
#include <cassert>
using namespace xos::cow;
int main() {
    snapshot_page rw{true,false,true,true,true,true,true,false,false,1};
    assert(classify_snapshot(rw)==snapshot_action::writable_cow);
    auto cow=rw; cow.hardware_writable=false; cow.cow=true; cow.references=2;
    assert(classify_snapshot(cow)==snapshot_action::writable_cow);
    auto ro=rw; ro.hardware_writable=false; ro.logical_writable=false;
    assert(classify_snapshot(ro)==snapshot_action::readonly);
    ro.executable=true; assert(classify_snapshot(ro)==snapshot_action::readonly);
    auto hidden=ro; hidden.present=false; hidden.hidden=true; hidden.executable=false;
    assert(classify_snapshot(hidden)==snapshot_action::hidden);
    auto invalid=rw; invalid.references=0; assert(classify_snapshot(invalid)==snapshot_action::invalid);
    invalid=rw; invalid.references=~xos::u32{0}; assert(classify_snapshot(invalid)==snapshot_action::invalid);
    invalid=rw; invalid.parent_user=false; assert(classify_snapshot(invalid)==snapshot_action::invalid);
    invalid=rw; invalid.parent_writable=false; assert(classify_snapshot(invalid)==snapshot_action::invalid);
    invalid=rw; invalid.executable=true; assert(classify_snapshot(invalid)==snapshot_action::invalid);
    invalid=rw; invalid.references=2; assert(classify_snapshot(invalid)==snapshot_action::invalid);
    invalid=cow; invalid.hardware_writable=true; assert(classify_snapshot(invalid)==snapshot_action::invalid);
    invalid=hidden; invalid.cow=true; assert(classify_snapshot(invalid)==snapshot_action::invalid);
    invalid=rw; invalid.hidden=true; assert(classify_snapshot(invalid)==snapshot_action::invalid);
    invalid=rw; invalid.present=false; assert(classify_snapshot(invalid)==snapshot_action::invalid);
}
