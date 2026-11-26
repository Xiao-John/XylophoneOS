/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_RTLD_INITIAL_TLS_H
#define XOS_RTLD_INITIAL_TLS_H
#include <stddef.h>

struct link_map;
void *__xos_rtld_init_tls (size_t) attribute_hidden;
void __xos_rtld_init_tls_templates (struct link_map *, void *) attribute_hidden;

#endif
