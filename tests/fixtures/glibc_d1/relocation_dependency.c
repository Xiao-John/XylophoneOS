/* SPDX-License-Identifier: Apache-2.0 */
#include <stdint.h>

#ifdef D1_TLS_PROVIDER
extern int *__errno_location (void);
_Alignas (64) _Thread_local uint64_t provider_tls = 0x51;
static _Thread_local uint64_t calls;

uint64_t
d1_dependency (uint64_t change)
{
  int *value = __errno_location ();
  uint64_t previous = provider_tls + calls + 256 * (unsigned int) *value;
  *value += change;
  calls += change;
  return previous;
}
#else
extern _Thread_local uint64_t provider_tls;
static _Alignas (256) _Thread_local volatile uint64_t own_tls = 0xa7;
static _Thread_local uint64_t changes;

uint64_t
d1_dependency (uint64_t change)
{
  uint64_t previous = provider_tls + own_tls + changes;
  provider_tls += change;
  changes += change;
  return previous;
}
#endif
