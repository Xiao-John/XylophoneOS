/* SPDX-License-Identifier: Apache-2.0 */
#pragma once
#ifndef DASH_BUILTINS_ONLY
#include <sys/types.h>
#include <sys/stat.h>
#include <spawn.h>
#include <stdint.h>
/* FAT has no symbolic links. Keep the adaptation local to this port. */
#define lstat stat
#define HAVE_KILLPG 1
static inline uint32_t xos_htonl(uint32_t value) { return __builtin_bswap32(value); }
#define htonl xos_htonl
ssize_t xos_shell_read(int, void *, size_t);
union node;
extern int xos_pipeline_active, xos_pipeline_failed;
void xos_pipeline_begin(void);
int xos_pipeline_finish(int);
int xos_shell_foreground(const int *, unsigned, int);
void xos_shell_cancel(int);
int xos_evalpipe(union node *, int);
void xos_check_tree(union node *);
int xos_posix_spawn_driver(pid_t *, const char *, const posix_spawn_file_actions_t *,
                           const posix_spawnattr_t *, char *const[], char *const[]);
#endif
