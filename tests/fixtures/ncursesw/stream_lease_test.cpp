// SPDX-License-Identifier: Apache-2.0
#include "stream_lease.hpp"
using namespace xos;

int main() {
    stream_lease lease;
    if (lease.active() || lease.holder() || lease.claim(0) || !lease.claim(1)) return 1;
    if (!lease.active() || lease.claim(2) || lease.delegate(2, 3) || lease.delegate(1, 1)) return 2;
    if (!lease.delegate(1, 2) || !lease.delegate(2, 3) || lease.delegate(1, 4)) return 3;
    if (!lease.contains(1) || !lease.contains(2) || lease.contains(4)) return 4;
    if (lease.reclaim(4) || !lease.reclaim(2) || lease.holder() != 2) return 5;
    if (!lease.delegate(2, 3) || !lease.reclaim(3) || lease.holder() != 2) return 6;
    if (!lease.delegate(2, 3) || !lease.remove(2) || lease.holder() != 1 || lease.contains(3)) return 7;
    for (u64 i = 2; i <= 8; ++i) if (!lease.delegate(i - 1, i)) return 8;
    if (lease.delegate(8, 9) || !lease.reclaim(1) || lease.holder() != 1) return 9;
    if (!lease.remove(1) || !lease.active() || lease.holder() || lease.claim(4)) return 10;
    return 0;
}
