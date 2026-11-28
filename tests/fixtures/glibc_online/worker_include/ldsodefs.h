/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TEST_LDSODEFS_H
#define TEST_LDSODEFS_H
#include <stdbool.h>
#include <stddef.h>
extern size_t dl_tls_static_size, dl_tls_static_align;
#define GLRO(name) (name)
void *_dl_allocate_tls (void *);
void _dl_deallocate_tls (void *, bool);
#endif
