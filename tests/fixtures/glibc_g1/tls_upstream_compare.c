/* SPDX-License-Identifier: Apache-2.0
   Compare XOS reserved-TLS placement with the actual upstream glibc helper. */
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "xos_thread_create.h"
static size_t dl_tls_static_size, dl_tls_static_align;
#define GLRO(name) (name)
#define TLS_TCB_AT_TP 1
#define TLS_DTV_AT_TP 0
#define TLS_TCB_SIZE 128
#define roundup(x, a) (((x) + (a) - 1) & ~((a) - 1))
#include "dl-tls_block_align.h"
xos_i64 __xos_thread_test_call (xos_u64 n, xos_u64 a, xos_u64 b)
{ (void)n; (void)a; (void)b; assert (0); return 0; }
int main (void)
{
  _Alignas(4096) unsigned char storage[32768];
  for (size_t alignment = 16; alignment <= 4096; alignment *= 2)
    for (size_t offset = 0; offset < 257; ++offset)
      for (size_t units = 0; units < 3; ++units)
        {
          dl_tls_static_align = alignment;
          dl_tls_static_size = units * alignment + TLS_TCB_SIZE;
          size_t size = _dl_tls_block_size_with_pre ();
          void *allocated = storage + offset;
          struct xos_thread_reservation r = {0};
          r.tls_begin = (uintptr_t) allocated;
          r.tls_end = (uintptr_t) storage + sizeof storage;
          struct xos_thread_tls_layout layout;
          assert (__xos_thread_tls_layout (&r, size, alignment, TLS_TCB_SIZE, &layout) == 0);
          void *expected = _dl_tls_block_align (size, allocated);
          assert (layout.thread_pointer == (uintptr_t) expected);
          assert (layout.static_begin % alignment == 0);
          assert (layout.descriptor_end <= r.tls_end);
        }
}
