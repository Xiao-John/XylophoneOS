// SPDX-License-Identifier: Apache-2.0
#include "../../../src/user/ssg/page_continuity.hpp"
#include <cassert>
using ssg_pipe::PageContinuity;
int main() {
    PageContinuity good;
    assert(good.accept("i", "e", "r", 1, 0, false, "a"));
    assert(good.accept("i", "e", "r", 2, 0, true, ""));
    assert(!good.accept("i", "e", "r", 3, 0, true, ""));
    for (int fault = 0; fault < 9; ++fault) {
        PageContinuity c;
        assert(c.accept("i", "e", "r", 1, 0, false, "a"));
        assert(!c.accept(fault == 0 ? "other" : "i", fault == 1 ? "other" : "e",
                         fault == 2 ? "other" : "r", fault == 3 ? 3 : 2,
                         fault == 4 ? 1 : fault == 5 ? -1 : 0,
                         fault == 6, fault == 6 ? "not-empty" : fault == 7 ? "a" : ""));
    }
    PageContinuity empty;
    assert(!empty.accept("", "e", "r", 1, 0, true, ""));
}
