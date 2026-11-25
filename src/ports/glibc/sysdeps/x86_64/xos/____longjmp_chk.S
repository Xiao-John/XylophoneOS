/* SPDX-License-Identifier: Apache-2.0
   XOS has no alternate signal stack.  Reject restoration of a frame
   below the active stack pointer instead of issuing Linux sigaltstack. */
#define CHECK_INVALID_LONGJMP \
    cmp %R8_LP, %RSP_LP; \
    jbe .Lxos_valid_longjmp; \
    ud2; \
.Lxos_valid_longjmp:
#define __longjmp ____longjmp_chk
#include <__longjmp.S>
