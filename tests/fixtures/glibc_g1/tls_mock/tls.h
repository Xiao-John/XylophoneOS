/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TEST_TLS_H
#define TEST_TLS_H
#include <stddef.h>
struct pthread {
  struct { void *self, *tcb; int multiple_threads; void *dtv; } header;
  void *specific[2];
  char specific_1stblock[32];
  int setxid_futex;
};
#define TLS_TCB_AT_TP 1
#define TLS_DTV_AT_TP 0
#define TLS_TCB_SIZE sizeof (struct pthread)
#define TLS_TPADJ(pd) (pd)
typedef union { size_t counter; void *pointer[2]; } dtv_t;
#endif
